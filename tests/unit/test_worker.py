import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.infrastructure.content.job_repositories import SqlAlchemyContentIngestionJobRepository
from app.worker import (
    _run_loop,
    check_worker_health,
    retry_delay_seconds,
    run_dispatch_pass,
    run_retry_pass,
    write_health_state,
)


@pytest.mark.parametrize(
    ("attempt", "random_value", "expected"),
    [
        (1, 0, 24),
        (1, 0.5, 30),
        (1, 1, 36),
        (2, 0.5, 60),
        (10, 0.5, 900),
        (100_000, 0.5, 900),
    ],
)
def test_retry_delay_is_exponential_capped_and_jittered(attempt, random_value, expected):
    assert retry_delay_seconds(attempt, 30, 900, random_value) == expected


@pytest.mark.parametrize(
    ("attempt", "base", "cap", "sample"),
    [(0, 30, 900, 0.5), (1, 0, 900, 0.5), (1, 30, 10, 0.5), (1, 30, 900, 1.1)],
)
def test_retry_delay_rejects_invalid_parameters(attempt, base, cap, sample):
    with pytest.raises(ValueError):
        retry_delay_seconds(attempt, base, cap, sample)


def test_worker_health_requires_each_loop_to_finish_within_three_intervals(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "worker_dispatch_interval_seconds", 2)
    monkeypatch.setattr(settings, "worker_retry_interval_seconds", 10)
    path = tmp_path / "health.json"
    write_health_state({"dispatch": 95, "retry": 71}, path)

    check_worker_health(now=100, path=path)
    with pytest.raises(RuntimeError, match="dispatch"):
        check_worker_health(now=102, path=path)
    with pytest.raises(RuntimeError, match="health file"):
        check_worker_health(now=102, path=tmp_path / "missing.json")


def test_worker_health_state_is_valid_json(tmp_path):
    path = tmp_path / "health.json"
    write_health_state({"dispatch": 1.5, "retry": 2.5}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"dispatch": 1.5, "retry": 2.5}


def test_worker_settings_defaults_match_the_design():
    settings = Settings(_env_file=None, app_environment="testing")
    assert (
        settings.worker_dispatch_interval_seconds,
        settings.worker_dispatch_batch,
        settings.worker_retry_interval_seconds,
        settings.worker_retry_batch,
        settings.worker_retry_base_seconds,
        settings.worker_retry_cap_seconds,
        settings.worker_shutdown_grace_seconds,
    ) == (2, 20, 10, 50, 30, 900, 25)


@pytest.mark.parametrize(
    "values",
    [
        {"worker_dispatch_interval_seconds": 0},
        {"worker_dispatch_batch": 0},
        {"worker_retry_base_seconds": 0},
        {"worker_retry_cap_seconds": 0},
        {"worker_retry_base_seconds": 901},
        {"worker_retry_cap_seconds": 86401},
        {"worker_stuck_processing_seconds": 0},
        {"worker_stuck_stage_seconds": 0},
        {"worker_max_in_flight_seconds": 0},
        {"worker_orphan_grace_seconds": 3599},
        {"worker_orphan_sweep_interval_seconds": 0},
        {"worker_shutdown_grace_seconds": 0},
    ],
)
def test_worker_settings_reject_out_of_range_values(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_environment="testing", **values)


@pytest.mark.asyncio
async def test_dispatch_claim_selects_exactly_one_oldest_due_row_with_skip_locked():
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    await SqlAlchemyContentIngestionJobRepository(session).claim_next_due_dispatch({"skip-me"})

    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
    assert "limit" in sql and "limit %(param" in sql
    assert "for update skip locked" in sql
    assert "order by content_ingestion_jobs.created_at asc" in sql
    assert "content_ingestion_jobs.id not in" in sql


@pytest.mark.asyncio
async def test_retrier_claim_skips_permanent_failures_and_attempts_at_the_cap():
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    await SqlAlchemyContentIngestionJobRepository(session).claim_next_retryable_failure(set())

    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
    assert "for update skip locked" in sql
    assert "content_ingestion_jobs.is_retryable is true" in sql
    assert "content_ingestion_jobs.attempt_count < content_ingestion_jobs.max_attempts" in sql
    assert "order by content_ingestion_jobs.updated_at asc" in sql


@pytest.mark.asyncio
async def test_failing_claim_is_excluded_for_the_rest_of_the_dispatch_tick(monkeypatch):
    import app.worker as worker

    monkeypatch.setattr(worker.settings, "worker_dispatch_batch", 5)
    seen: list[set[str]] = []

    async def dispatch(excluded: set[str], claimed: list[str]) -> bool:
        seen.append(set(excluded))
        if "bad-job" not in excluded:
            claimed.append("bad-job")
            raise RuntimeError("expected test failure")
        if "good-job" not in excluded:
            claimed.append("good-job")
            return True
        return False

    monkeypatch.setattr(worker, "_dispatch_one", dispatch)
    await run_dispatch_pass()
    assert seen == [set(), {"bad-job"}, {"bad-job", "good-job"}]


@pytest.mark.asyncio
async def test_failing_claim_is_excluded_for_the_rest_of_the_retry_tick(monkeypatch):
    import app.worker as worker

    monkeypatch.setattr(worker.settings, "worker_retry_batch", 5)
    seen: list[set[str]] = []

    async def retry(excluded: set[str], claimed: list[str]) -> bool:
        seen.append(set(excluded))
        if "bad-job" not in excluded:
            claimed.append("bad-job")
            raise RuntimeError("expected test failure")
        if "good-job" not in excluded:
            claimed.append("good-job")
            return True
        return False

    monkeypatch.setattr(worker, "_retry_one", retry)
    await run_retry_pass()
    assert seen == [set(), {"bad-job"}, {"bad-job", "good-job"}]


@pytest.mark.asyncio
async def test_dispatch_pass_does_not_claim_after_shutdown_is_requested(monkeypatch):
    import app.worker as worker

    claimed: list[str] = []

    async def dispatch(excluded: set[str], claimed_ids: list[str]) -> bool:
        claimed.append("unexpected")
        return False

    monkeypatch.setattr(worker, "_dispatch_one", dispatch)
    stop = asyncio.Event()
    stop.set()

    await run_dispatch_pass(stop)

    assert claimed == []


@pytest.mark.asyncio
async def test_loop_records_only_a_successful_pass_and_recovers_after_an_error(monkeypatch):
    import app.worker as worker

    stop = asyncio.Event()
    completed: dict[str, float] = {}
    calls = 0
    states: list[dict[str, float]] = []

    async def pass_fn(_stop: asyncio.Event) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database unavailable")
        stop.set()

    monkeypatch.setattr(worker, "write_health_state", lambda state: states.append(dict(state)))
    await _run_loop("dispatch", 0, pass_fn, stop, completed)

    assert calls == 2
    assert "dispatch" in completed
    assert states == [completed]

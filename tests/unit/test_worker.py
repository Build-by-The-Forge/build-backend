import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.infrastructure.content.job_repositories import SqlAlchemyContentIngestionJobRepository
from app.infrastructure.db.models.content import ContentIngestionJobModel
from app.worker import (
    _run_loop,
    check_worker_health,
    retry_delay_seconds,
    run_dispatch_pass,
    run_recoverer_pass,
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
    monkeypatch.setattr(settings, "worker_recoverer_interval_seconds", 60)
    path = tmp_path / "health.json"
    write_health_state({"dispatch": 95, "retry": 71, "orphan_sweep": 95, "recoverer": 99}, path)

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
        settings.worker_dispatch_claim_seconds,
        settings.worker_retry_interval_seconds,
        settings.worker_retry_batch,
        settings.worker_retry_base_seconds,
        settings.worker_retry_cap_seconds,
        settings.worker_recoverer_interval_seconds,
        settings.worker_recoverer_batch,
        settings.worker_shutdown_grace_seconds,
        settings.worker_orphan_sweep_interval_seconds,
    ) == (2, 20, 120, 10, 50, 30, 900, 60, 20, 25, 3600)


@pytest.mark.parametrize(
    "values",
    [
        {"worker_dispatch_interval_seconds": 0},
        {"worker_dispatch_batch": 0},
        {"worker_dispatch_claim_seconds": 119},
        {"worker_dispatch_claim_seconds": 601},
        {"worker_retry_base_seconds": 0},
        {"worker_retry_cap_seconds": 0},
        {"worker_recoverer_interval_seconds": 0},
        {"worker_recoverer_batch": 0},
        {"worker_retry_base_seconds": 901},
        {"worker_retry_cap_seconds": 86401},
        {"worker_retry_base_seconds": 30, "worker_retry_cap_seconds": 29},
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
    assert "dispatch_claim_token is null" in sql
    assert "dispatch_claim_expires_at" in sql


@pytest.mark.asyncio
async def test_recoverer_claim_selects_one_overdue_active_job_with_skip_locked():
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    await SqlAlchemyContentIngestionJobRepository(session).claim_next_overdue_job(set(), 600, 1800, 3600)

    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
    assert "limit" in sql and "for update skip locked" in sql
    assert "content_ingestion_jobs.status in" in sql
    assert "content_ingestion_jobs.updated_at" in sql
    assert "content_ingestion_jobs.last_dispatched_at" in sql


@pytest.mark.asyncio
async def test_dispatch_claim_persists_a_unique_token_and_expiry():
    now = datetime.now(timezone.utc)
    model = ContentIngestionJobModel(
        id="job-1",
        asset_id="asset-1",
        source_id="source-1",
        tenant_id="tenant-1",
        run_number=1,
        status="queued",
        attempt_count=1,
        max_attempts=3,
        error_details={},
        is_retryable=False,
        metrics={},
        attempt_history=[],
        created_by="usr-1",
        created_at=now,
        updated_at=now,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = model
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()

    claimed = await SqlAlchemyContentIngestionJobRepository(session).claim_next_due_dispatch(set(), claim_seconds=120)

    assert claimed is not None
    assert claimed.dispatch_claim_token
    assert claimed.dispatch_claim_expires_at is not None
    assert now + timedelta(seconds=119) < claimed.dispatch_claim_expires_at <= now + timedelta(seconds=121)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_wins", [False, True])
async def test_worker_commits_claim_before_dispatch_and_ignores_response_after_callback(monkeypatch, callback_wins):
    import app.worker as worker
    from app.application.content.job_handlers import DispatchAttemptOutcome
    from app.domain.content.job import ContentIngestionJob

    job = ContentIngestionJob.create(
        asset_id="asset-1",
        source_id="source-1",
        tenant_id="tenant-1",
        created_by="usr-1",
    )
    job.queue()
    job.dispatch_claim_token = "worker-token"
    job.dispatch_claim_expires_at = datetime.now(timezone.utc) + timedelta(seconds=120)
    state = {"open_transactions": 0, "claim_committed": False, "uow_count": 0}
    asset = object()
    source = object()

    class FakeUnitOfWork:
        def __init__(self, _session):
            state["uow_count"] += 1
            self.index = state["uow_count"]
            self.jobs = self
            self.assets = self
            self.sources = self

        async def __aenter__(self):
            state["open_transactions"] += 1
            return self

        async def __aexit__(self, *_args):
            state["open_transactions"] -= 1
            if self.index == 1:
                state["claim_committed"] = True

        async def claim_next_due_dispatch(self, _excluded, claim_seconds):
            assert claim_seconds == 120
            return job

        async def get_asset_by_id(self, _asset_id):
            return asset

        async def get_source_by_id(self, _source_id):
            return source

        async def get_job_for_update(self, _job_id):
            return job

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    class FakeDispatcher:
        def __init__(self, *_args, **_kwargs):
            pass

        async def attempt_dispatch(self, _job, _asset, _source, _actor, *, claim_token):
            assert claim_token == "worker-token"
            assert state["claim_committed"] is True
            assert state["open_transactions"] == 0
            if callback_wins:
                job.apply_callback(
                    event_type="stage_progress",
                    stage="extracted",
                    run_number=job.run_number,
                    attempt_count=job.attempt_count,
                    external_task_id="task-1",
                    metrics={"characters": 10, "pages": 1, "method": "native_text"},
                )
            return DispatchAttemptOutcome(external_task_id="task-1")

        async def record_dispatch_outcome(self, current, _asset, outcome, *, claim_token):
            assert not callback_wins
            assert state["open_transactions"] == 1
            current.record_dispatch(outcome.external_task_id, claim_token=claim_token)
            return current

    monkeypatch.setattr(worker, "SessionLocal", FakeSessionContext)
    monkeypatch.setattr(worker, "ContentUnitOfWork", FakeUnitOfWork)
    monkeypatch.setattr(worker, "DispatchIngestionJobHandler", FakeDispatcher)
    monkeypatch.setattr(worker, "HttpAIServiceIngestionGateway", lambda: object())
    monkeypatch.setattr(worker, "EventBus", lambda: object())
    monkeypatch.setattr(worker, "set_transaction_timeouts", AsyncMock())

    claimed: list[str] = []
    assert await worker._dispatch_one(set(), claimed) is True
    assert claimed == [job.id]
    if callback_wins:
        assert job.status.value == "extracted"
        assert job.dispatch_claim_token is None
    else:
        assert job.external_task_id == "task-1"
    assert state["open_transactions"] == 0


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
async def test_failing_claim_is_excluded_for_the_rest_of_the_recovery_tick(monkeypatch):
    import app.worker as worker

    monkeypatch.setattr(worker.settings, "worker_recoverer_batch", 5)
    seen: list[set[str]] = []

    async def recover(excluded: set[str], claimed: list[str]) -> bool:
        seen.append(set(excluded))
        if "bad-job" not in excluded:
            claimed.append("bad-job")
            raise RuntimeError("expected test failure")
        if "good-job" not in excluded:
            claimed.append("good-job")
            return True
        return False

    monkeypatch.setattr(worker, "_recover_one", recover)
    await run_recoverer_pass()
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
async def test_recovery_pass_does_not_claim_after_shutdown_is_requested(monkeypatch):
    import app.worker as worker

    claimed: list[str] = []

    async def recover(excluded: set[str], claimed_ids: list[str]) -> bool:
        claimed.append("unexpected")
        return False

    monkeypatch.setattr(worker, "_recover_one", recover)
    stop = asyncio.Event()
    stop.set()

    await run_recoverer_pass(stop)
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

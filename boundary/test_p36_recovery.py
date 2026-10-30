"""P3-6 7b: ingestion stays correct through worker death, record loss and
the ownership-check / recovery race (design §7.1, §7.5, §14).

These run only in the gate's fault phase (scripts/m3_boundary_gate.sh),
against ai-worker-faults: the AI worker with the test-only pause points,
held and released through files in BOUNDARY_FAULT_DIR. Selected without
that directory, they fail rather than skip.

Every assertion message carries an evidence snapshot taken before the test
changes anything else: the job row, the AI fence, the chunks by attempt,
the task record and the callback ledger.

The race, in both orderings. Since ai-service #34, a worker whose task
record is gone cannot report anything, so the attempt that loses its record
never makes the job ready:
- the effect wins: its index write commits before the record is lost; its
  indexed report is then refused, recovery fails the attempt as
  AI_TASK_LOST, and attempt 2 replaces the chunks and makes the job ready;
- recovery wins: the record is lost while the write is held past its
  ownership check; recovery dispatches attempt 2, which raises the fence;
  then the held write runs and the database refuses it (STALE_INDEX_WRITE).
  Local cancellation is not what stops it: the pause point models a write
  already in flight.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from redis import Redis

from boundary.conftest import (
    AI_APP_DSN,
    CALLBACK_PATH,
    create_asset,
    create_job_for,
    jbytes,
    pdf_document,
    system_context,
    to_ai,
    to_backend,
    user_context,
)

BACKEND_APP_DSN = os.environ.get("BOUNDARY_BACKEND_APP_DSN", "")
FAULT_DIR = os.environ.get("BOUNDARY_FAULT_DIR", "")
BEFORE_INDEX_WRITE = "before_index_write"
AFTER_INDEX_WRITE = "after_index_write"
C23_STATE = "c23.json"
RECOVERY_TIMEOUT = 240
BODY = [
    "Kirchhoff's current law states that the currents entering a junction",
    "sum to the currents leaving it, because charge is conserved there.",
    "The voltage law adds the potential differences around any closed loop to zero.",
]
QUESTION = "Why must the currents into a junction equal the currents out?"


# --- the harness -------------------------------------------------------------------


@pytest.fixture
def faults() -> Path:
    if not FAULT_DIR or not Path(FAULT_DIR).is_dir():
        pytest.fail("BOUNDARY_FAULT_DIR is required: run these in the gate's fault phase")
    return Path(FAULT_DIR)


def arm(faults: Path, point: str) -> None:
    (faults / f"{point}.pause").write_text("", encoding="utf-8")


def release(faults: Path, point: str) -> None:
    (faults / f"{point}.pause").unlink(missing_ok=True)


def wait_reached(faults: Path, point: str, job_id: str, timeout: float = 120) -> None:
    marker = faults / f"{point}.{job_id}.reached"
    deadline = time.time() + timeout
    while not marker.exists():
        if time.time() > deadline:
            pytest.fail(f"{point} was not reached for job {job_id} within {timeout} s")
        time.sleep(0.2)


def _fetch(dsn: str, statement: str, *args) -> list[asyncpg.Record]:
    async def go():
        connection = await asyncpg.connect(dsn)
        try:
            return await connection.fetch(statement, *args)
        finally:
            await connection.close()

    return asyncio.run(go())


def chunks_by_attempt(tenant_id: str, asset_id: str) -> dict[tuple[int, int], int]:
    rows = _fetch(
        AI_APP_DSN,
        "SELECT run_number, attempt, count(*) AS n FROM document_chunks"
        " WHERE tenant_id = $1 AND asset_id = $2 GROUP BY run_number, attempt",
        tenant_id,
        asset_id,
    )
    return {(r["run_number"], r["attempt"]): r["n"] for r in rows}


def fence(tenant_id: str, asset_id: str) -> tuple[int, int] | None:
    rows = _fetch(
        AI_APP_DSN,
        "SELECT run_number, attempt FROM ingestion_fences WHERE tenant_id = $1 AND asset_id = $2",
        tenant_id,
        asset_id,
    )
    return (rows[0]["run_number"], rows[0]["attempt"]) if rows else None


def job_row(job_id: str) -> dict[str, Any]:
    [row] = _fetch(
        BACKEND_APP_DSN,
        "SELECT status, run_number, attempt_count, external_task_id, error_code, attempt_history,"
        " last_dispatched_at, updated_at FROM content_ingestion_jobs WHERE id = $1",
        job_id,
    )
    record = dict(row)
    if isinstance(record["attempt_history"], str):
        record["attempt_history"] = json.loads(record["attempt_history"])
    return record


def ledger(job_id: str) -> list[tuple[int | None, str | None, str | None, str, str]]:
    rows = _fetch(
        BACKEND_APP_DSN,
        "SELECT attempt_count, event_type, stage, outcome, received_at FROM content_ingestion_events"
        " WHERE job_id = $1 ORDER BY received_at",
        job_id,
    )
    return [(r["attempt_count"], r["event_type"], r["stage"], r["outcome"], str(r["received_at"])) for r in rows]


def ai_redis() -> Redis:
    return Redis.from_url(os.environ["BOUNDARY_AI_REDIS_URL"], decode_responses=True)


def task_key(task_id: str) -> str:
    return f"{{ai-tasks}}:ingest:task:{task_id}"


def evidence(job_id: str, tenant_id: str, asset_id: str, task_id: str | None = None) -> str:
    """Everything needed to diagnose a failure, read before anything changes."""
    snapshot: dict[str, Any] = {
        "job": job_row(job_id),
        "fence": fence(tenant_id, asset_id),
        "chunks_by_attempt": {f"{r}/{a}": n for (r, a), n in chunks_by_attempt(tenant_id, asset_id).items()},
        "ledger": ledger(job_id),
        "at": time.time(),
    }
    if task_id:
        with ai_redis() as client:
            snapshot["task_record"] = client.hgetall(task_key(task_id))
    return json.dumps(snapshot, default=str, indent=1)


def lose_task_record(task_id: str) -> None:
    with ai_redis() as client:
        assert client.delete(task_key(task_id)) == 1, f"no task record {task_id}"


def wait_until(condition, describe, timeout: float = RECOVERY_TIMEOUT) -> None:
    deadline = time.time() + timeout
    while not condition():
        if time.time() > deadline:
            pytest.fail(f"timed out after {timeout} s: {describe()}")
        time.sleep(0.5)


def stale_replay(job_id: str, tenant_id: str, task_id: str, run: int, attempt: int, backend) -> dict[str, Any]:
    """The superseded attempt's late callback, signed as AI-service sends it."""
    body = {
        "job_id": job_id,
        "event_id": str(uuid.uuid4()),
        "event_type": "stage_progress",
        "stage": "indexed",
        "external_task_id": task_id,
        "run_number": run,
        "attempt_count": attempt,
        "metrics": {"indexed_chunks": 1, "index": "document_chunks"},
    }
    raw = jbytes(body)
    response = backend.post(CALLBACK_PATH, content=raw, headers=to_backend(CALLBACK_PATH, raw, system_context(tenant_id)))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def assert_ready_on_attempt_2_only(job_id: str, tenant_id: str, asset_id: str) -> None:
    row = job_row(job_id)
    snapshot = evidence(job_id, tenant_id, asset_id)
    assert (row["status"], row["run_number"], row["attempt_count"]) == ("ready", 1, 2), snapshot
    assert [h["error_code"] for h in row["attempt_history"]] == ["AI_TASK_LOST"], snapshot
    assert row["attempt_history"][0]["attempt"] == 1, snapshot
    chunks = chunks_by_attempt(tenant_id, asset_id)
    assert set(chunks) == {(1, 2)} and chunks[(1, 2)] >= 1, snapshot  # only the winner's chunks
    assert fence(tenant_id, asset_id) == (1, 2), snapshot


def retrieve(ai, tenant, role: str) -> list[dict]:
    member = tenant.members[role]
    raw = jbytes({"query": QUESTION})
    context = user_context(tenant.tenant_id, member.user_id, ["ai.use"], membership_id=member.membership_id, role=role)
    response = ai.post("/v1/ai/retrieve", content=raw, headers=to_ai("POST", "/v1/ai/retrieve", raw, context))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def assert_tenant_isolated(ai, tenant_a, tenant_b, asset_id: str) -> None:
    source = f"asset:{asset_id}"
    own = [r for r in retrieve(ai, tenant_a, "student") if r["provenance"]["source_uri"] == source]
    assert own, "the ready document is retrievable by its own tenant"
    assert not [r for r in retrieve(ai, tenant_b, "lecturer") if r["provenance"]["source_uri"] == source]


def start_job(backend, tenant) -> tuple[dict, dict]:
    asset = create_asset(backend, tenant, pdf_document(uuid.uuid4().hex, BODY))
    return asset, create_job_for(backend, tenant, asset)


# --- the race, both orderings --------------------------------------------------------


@pytest.mark.fault_injection
def test_race_the_effect_wins_then_recovery_replaces_it(ai, backend, tenant_a, tenant_b, faults):
    arm(faults, AFTER_INDEX_WRITE)
    try:
        asset, job = start_job(backend, tenant_a)
        tenant, asset_id, job_id = tenant_a.tenant_id, asset["id"], job["id"]
        wait_reached(faults, AFTER_INDEX_WRITE, job_id)
        row = job_row(job_id)
        task_1 = row["external_task_id"]
        snapshot = evidence(job_id, tenant, asset_id, task_1)
        # Attempt 1's write has committed under its own fence.
        assert set(chunks_by_attempt(tenant, asset_id)) == {(1, 1)}, snapshot
        assert fence(tenant, asset_id) == (1, 1), snapshot
        assert row["status"] != "ready", snapshot
        lose_task_record(task_1)
    finally:
        release(faults, AFTER_INDEX_WRITE)

    # Attempt 1 cannot report indexed without its record; recovery runs attempt 2.
    wait_until(
        lambda: job_row(job_id)["status"] in ("ready", "failed") and job_row(job_id)["attempt_count"] == 2,
        lambda: evidence(job_id, tenant, asset_id, task_1),
    )
    assert_ready_on_attempt_2_only(job_id, tenant, asset_id)
    # The superseded attempt's late callback is stale and changes nothing.
    before = job_row(job_id)
    assert stale_replay(job_id, tenant, task_1, 1, 1, backend)["outcome"] == "stale"
    assert job_row(job_id)["status"] == before["status"] == "ready"
    assert_tenant_isolated(ai, tenant_a, tenant_b, asset_id)


@pytest.mark.fault_injection
def test_race_recovery_wins_and_the_database_fence_refuses_the_late_write(ai, backend, tenant_a, tenant_b, faults):
    arm(faults, BEFORE_INDEX_WRITE)
    released = False
    try:
        asset, job = start_job(backend, tenant_a)
        tenant, asset_id, job_id = tenant_a.tenant_id, asset["id"], job["id"]
        wait_reached(faults, BEFORE_INDEX_WRITE, job_id)
        task_1 = job_row(job_id)["external_task_id"]
        snapshot = evidence(job_id, tenant, asset_id, task_1)
        assert chunks_by_attempt(tenant, asset_id) == {}, snapshot  # held past its check, not yet written
        assert fence(tenant, asset_id) == (1, 1), snapshot
        lose_task_record(task_1)

        # Recovery wins: attempt 1 fails as lost, and attempt 2's dispatch
        # raises the fence while attempt 1's write is still held.
        wait_until(
            lambda: job_row(job_id)["attempt_count"] == 2 and fence(tenant, asset_id) == (1, 2),
            lambda: evidence(job_id, tenant, asset_id, task_1),
        )
        snapshot = evidence(job_id, tenant, asset_id, task_1)
        assert chunks_by_attempt(tenant, asset_id) == {}, snapshot
        assert job_row(job_id)["status"] != "ready", snapshot

        release(faults, BEFORE_INDEX_WRITE)
        released = True
        # The held write now runs against fence (1, 2) and is refused; attempt
        # 1's chunks must never appear, before or after attempt 2 writes.
        seen: set[tuple[int, int]] = set()

        def settled() -> bool:
            seen.update(chunks_by_attempt(tenant, asset_id))
            return job_row(job_id)["status"] in ("ready", "failed")

        wait_until(settled, lambda: evidence(job_id, tenant, asset_id, task_1))
        assert (1, 1) not in seen, evidence(job_id, tenant, asset_id)
    finally:
        if not released:
            release(faults, BEFORE_INDEX_WRITE)

    assert_ready_on_attempt_2_only(job_id, tenant, asset_id)
    assert stale_replay(job_id, tenant, task_1, 1, 1, backend)["outcome"] == "stale"
    assert_tenant_isolated(ai, tenant_a, tenant_b, asset_id)


# --- C23: the AI worker is killed mid-job ----------------------------------------------


@pytest.mark.c23_prepare
def test_c23_prepare_a_job_held_mid_ingestion(backend, tenant_a, faults):
    """Holds attempt 1 in the AI worker; the gate then SIGKILLs the worker,
    disarms the point and restarts it (scripts/m3_boundary_gate.sh)."""
    arm(faults, BEFORE_INDEX_WRITE)
    asset, job = start_job(backend, tenant_a)
    wait_reached(faults, BEFORE_INDEX_WRITE, job["id"])
    row = job_row(job["id"])
    assert row["status"] in ("processing", "extracted", "chunked") and row["attempt_count"] == 1, row
    (faults / C23_STATE).write_text(
        json.dumps(
            {
                "job_id": job["id"],
                "asset_id": asset["id"],
                "tenant_id": tenant_a.tenant_id,
                "task_id": row["external_task_id"],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.c23_verify
def test_c23_the_killed_attempt_is_recovered_as_attempt_2(backend, faults):
    state = json.loads((faults / C23_STATE).read_text(encoding="utf-8"))
    job_id, asset_id, tenant, task_1 = state["job_id"], state["asset_id"], state["tenant_id"], state["task_id"]
    assert not (faults / f"{BEFORE_INDEX_WRITE}.pause").exists(), "the gate disarms the point before restarting"

    # attempt 1 -> worker killed -> lease expires -> AI_TASK_LOST -> attempt 2 -> ready
    wait_until(
        lambda: job_row(job_id)["status"] in ("ready", "failed") and job_row(job_id)["attempt_count"] == 2,
        lambda: evidence(job_id, tenant, asset_id, task_1),
    )
    assert_ready_on_attempt_2_only(job_id, tenant, asset_id)
    # The killed attempt's late callback is rejected as stale.
    assert stale_replay(job_id, tenant, task_1, 1, 1, backend)["outcome"] == "stale"
    assert job_row(job_id)["status"] == "ready"

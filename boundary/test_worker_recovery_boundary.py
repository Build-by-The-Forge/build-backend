"""C23: a killed AI worker is recovered and the newer attempt owns the index."""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest

from boundary.conftest import (
    AI_APP_DSN,
    CALLBACK_PATH,
    create_asset,
    create_job_for,
    get_job,
    jbytes,
    pdf_document,
    system_context,
    to_backend,
    wait_for_status,
)

KILL_MARKER = "P36_WORKER_KILL_BOUNDARY_MARKER"


def callback_event(job: dict, **overrides) -> dict:
    body = {
        "job_id": job["id"],
        "event_id": str(uuid.uuid4()),
        "event_type": "stage_progress",
        "stage": "indexed",
        "external_task_id": job["external_task_id"],
        "run_number": job["run_number"],
        "attempt_count": job["attempt_count"],
        "metrics": {"chunks": 1, "indexed_chunks": 1, "index": "document_chunks"},
    }
    body.update(overrides)
    return body


def post_callback(backend, body: dict, tenant_id: str):
    raw = jbytes(body)
    headers = to_backend(CALLBACK_PATH, raw, system_context(tenant_id))
    return backend.post(CALLBACK_PATH, content=raw, headers=headers)


@pytest.mark.worker_kill
def test_c23_killed_ai_worker_recovers_on_attempt_two(backend, tenant_a):
    asset = create_asset(
        backend, tenant_a, pdf_document(uuid.uuid4().hex, [KILL_MARKER])
    )
    job = create_job_for(backend, tenant_a, asset)

    first = wait_for_status(backend, tenant_a, job["id"], {"processing"}, timeout=60)
    assert first["external_task_id"], first
    old_task_id = first["external_task_id"]

    final = wait_for_status(
        backend, tenant_a, job["id"], {"ready", "failed"}, timeout=300
    )

    assert final["status"] == "ready", final
    assert final["attempt_count"] == 2, final
    assert final["attempt_history"], final
    assert final["attempt_history"][0]["error_code"] == "AI_TASK_LOST", final
    assert final["external_task_id"] != old_task_id
    assert final["metrics"]["indexed_chunks"] == final["metrics"]["chunks"] >= 1

    async def indexed_attempts() -> list[asyncpg.Record]:
        connection = await asyncpg.connect(AI_APP_DSN)
        try:
            return await connection.fetch(
                """
                SELECT attempt, count(*) AS chunk_count
                FROM document_chunks
                WHERE tenant_id = $1 AND asset_id = $2
                GROUP BY attempt
                ORDER BY attempt
                """,
                tenant_a.tenant_id,
                asset["id"],
            )
        finally:
            await connection.close()

    indexed = asyncio.run(indexed_attempts())
    assert len(indexed) == 1, indexed
    assert indexed[0]["attempt"] == 2, indexed
    assert indexed[0]["chunk_count"] == final["metrics"]["indexed_chunks"]

    stale = post_callback(
        backend,
        callback_event(
            {**job, "external_task_id": old_task_id, "attempt_count": 1},
        ),
        tenant_a.tenant_id,
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["data"]["outcome"] == "stale"
    current = get_job(backend, tenant_a, job["id"])
    assert (current["status"], current["attempt_count"]) == ("ready", 2)

"""The real worker process finalizes an expired attempt with no client involved.

Reads the database directly, because any attempt route would finalize it first
and hide whether the worker did.
"""

import asyncio
import os
import time

import asyncpg

from boundary.test_m5_contracts import published_assessment  # noqa: F401

BACKEND_APP_DSN = os.environ.get("BOUNDARY_BACKEND_APP_DSN", "")


def _fetchrow(sql: str, *args):
    async def go():
        connection = await asyncpg.connect(BACKEND_APP_DSN)
        try:
            return await connection.fetchrow(sql, *args)
        finally:
            await connection.close()

    return asyncio.run(go())


def test_the_worker_process_finalizes_an_expired_attempt(backend, tenant_a, published_assessment):  # noqa: F811
    assessment_id, _ = published_assessment
    student = tenant_a.h("student")
    started = backend.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    assert started.status_code in (200, 201), started.text
    attempt_id = started.json()["data"]["id"]

    _fetchrow("UPDATE assessment_attempts SET expires_at = now() - interval '1 minute' WHERE id = $1", attempt_id)

    deadline = time.time() + 20
    row = None
    while time.time() < deadline:
        row = _fetchrow("SELECT status, finalized_by FROM assessment_attempts WHERE id = $1", attempt_id)
        if row["status"] == "submitted":
            break
        time.sleep(0.5)

    assert row["status"] == "submitted"
    assert row["finalized_by"] == "deadline"
    result = _fetchrow("SELECT count(*) AS n FROM assessment_attempt_results WHERE attempt_id = $1", attempt_id)
    assert result["n"] == 1

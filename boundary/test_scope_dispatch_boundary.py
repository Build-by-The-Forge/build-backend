"""The backend's scope-assignment dispatcher against the real AI service
(M3-D PR 5): a queued assignment is delivered by the running backend-worker,
signed so the AI service accepts it, and acknowledged; only then is the
document retrieved. A queued lowering is denied at once and delivered too.
"""

import asyncio
import os
import time
import uuid

import asyncpg
import pytest

from boundary.conftest import create_asset, create_job_for, pdf_document, wait_for_status
from boundary.test_scope_boundary import READY_TIMEOUT, served

DELIVERY_TIMEOUT = 90


def _db(statement: str, *args):
    async def go():
        connection = await asyncpg.connect(os.environ.get("BOUNDARY_BACKEND_APP_DSN", ""))
        try:
            return await connection.fetch(statement, *args)
        finally:
            await connection.close()

    return asyncio.run(go())


def queue(tenant, asset_id: str, scope: str, version: int) -> str:
    """What a classification or a revocation writes, in their transaction."""
    row = str(uuid.uuid4())
    _db(
        "INSERT INTO content_scope_assignments (id, tenant_id, asset_id, scope, version, lowers, reason, decided_by)"
        " VALUES ($1, $2, $3, $4, $5, $6, 'boundary', $7)",
        row,
        tenant.tenant_id,
        asset_id,
        scope,
        version,
        scope != "institutional",
        tenant.members["lecturer"].user_id,
    )
    return row


def settled(row: str) -> str | None:
    deadline = time.time() + DELIVERY_TIMEOUT
    while time.time() < deadline:
        [state] = _db("SELECT state FROM content_scope_assignments WHERE id = $1", row)
        if state["state"] != "pending":
            return state["state"]
        time.sleep(1)
    return None


@pytest.fixture(scope="module")
def own_ready_asset(backend, tenant_a) -> tuple[str, str]:
    marker = uuid.uuid4().hex
    asset = create_asset(backend, tenant_a, pdf_document(marker))
    job = create_job_for(backend, tenant_a, asset)
    final = wait_for_status(backend, tenant_a, job["id"], {"ready", "failed"}, timeout=READY_TIMEOUT)
    assert final["status"] == "ready", final
    return asset["id"], marker


def test_m3d_the_dispatcher_delivers_an_assignment_and_only_then_is_it_retrieved(ai, tenant_a, own_ready_asset):
    asset_id, marker = own_ready_asset
    assert not served(ai, tenant_a, asset_id, marker)  # ready, but never assigned: unknown

    row = queue(tenant_a, asset_id, "institutional", version=1000)
    assert settled(row) == "acknowledged"
    assert served(ai, tenant_a, asset_id, marker)


def test_m3d_a_queued_lowering_is_denied_at_once_and_then_delivered(ai, tenant_a, own_ready_asset):
    asset_id, marker = own_ready_asset
    assert served(ai, tenant_a, asset_id, marker)  # institutional from the test above

    row = queue(tenant_a, asset_id, "unknown", version=1001)
    # Pending, the backend sends it as denied on every call: excluded whatever the stored scope.
    assert not served(ai, tenant_a, asset_id, marker, denied=(asset_id,))
    assert settled(row) == "acknowledged"
    # Acknowledged, the stored scope alone keeps it out.
    assert not served(ai, tenant_a, asset_id, marker)

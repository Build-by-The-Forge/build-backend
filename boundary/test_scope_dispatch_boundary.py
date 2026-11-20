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

from boundary.conftest import (
    create_asset,
    create_job_for,
    jbytes,
    pdf_document,
    to_ai,
    user_context,
    wait_for_status,
)
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


DISPATCH = "/v1/ingest/dispatch"


def stated_dispatch(ai, tenant, asset: dict, **scope) -> tuple[int, dict]:
    """A signed dispatch for the asset as the backend builds one (M3-D PR 7)."""
    body = {
        "job_id": f"bnd-job-{uuid.uuid4().hex[:12]}",
        "asset_id": asset["id"],
        "source_id": asset["source_id"],
        "run_number": 1,
        "attempt_count": 1,
        "idempotency_key": f"bnd-{uuid.uuid4().hex}",
        "mime_type": "application/pdf",
        "content_sha256": asset["content_sha256"],
        "file_size_bytes": asset["file_size_bytes"],
        "storage_uri": asset["storage_uri"],
        "correlation_id": "boundary",
        **scope,
    }
    raw = jbytes({k: v for k, v in body.items() if v is not None})
    context = user_context(tenant.tenant_id, tenant.members["lecturer"].user_id, ["content.job.manage"])
    response = ai.post(DISPATCH, content=raw, headers=to_ai("POST", DISPATCH, raw, context))
    return response.status_code, response.json()


def test_m3d_pr7_a_dispatch_states_a_scope_the_ai_service_applies_by_version(ai, backend, tenant_a):
    asset = create_asset(backend, tenant_a)

    status, answer = stated_dispatch(ai, tenant_a, asset, scope="personal", scope_version=3)
    assert status == 202, answer
    assert (answer["data"]["scope"], answer["data"]["scope_version"]) == ("personal", 3)

    # Stating no decision, or an older one, changes nothing and reports what is held.
    for scope, version in (("unknown", 0), ("institutional", 2), ("unknown", 3)):
        status, answer = stated_dispatch(ai, tenant_a, asset, scope=scope, scope_version=version)
        assert status == 202, answer
        assert (answer["data"]["scope"], answer["data"]["scope_version"]) == ("personal", 3)

    # A newer decision is applied.
    status, answer = stated_dispatch(ai, tenant_a, asset, scope="unknown", scope_version=4)
    assert (answer["data"]["scope"], answer["data"]["scope_version"]) == ("unknown", 4)


def test_m3d_pr7_a_dispatch_without_a_valid_scope_is_refused_and_applies_nothing(ai, backend, tenant_a):
    asset = create_asset(backend, tenant_a)
    for scope in (
        {},
        {"scope": "personal"},
        {"scope_version": 1},
        {"scope": "public", "scope_version": 1},
        {"scope": "institutional", "scope_version": 0},
    ):
        status, _ = stated_dispatch(ai, tenant_a, asset, **scope)
        assert status == 422, scope
    # None of them left a scope: the first valid statement still starts from nothing.
    status, answer = stated_dispatch(ai, tenant_a, asset, scope="unknown", scope_version=0)
    assert (answer["data"]["scope"], answer["data"]["scope_version"]) == ("unknown", 0)


def test_m3d_pr7_another_tenants_asset_is_never_given_a_scope(ai, backend, tenant_a, tenant_b):
    asset = create_asset(backend, tenant_a)
    assert stated_dispatch(ai, tenant_a, asset, scope="personal", scope_version=1)[0] == 202
    status, _ = stated_dispatch(ai, tenant_b, asset, scope="institutional", scope_version=9)
    assert status in (403, 409)
    status, answer = stated_dispatch(ai, tenant_a, asset, scope="unknown", scope_version=0)
    assert (answer["data"]["scope"], answer["data"]["scope_version"]) == ("personal", 1)

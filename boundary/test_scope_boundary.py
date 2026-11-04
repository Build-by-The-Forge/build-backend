"""M3-D's first AI PR at the boundary: what the real AI service retrieves,
and what it signs.

- A ready document is `unknown` until the backend's signed assignment makes
  it institutional; `personal` and lowered documents are never returned, and
  a document in `denied_assets` is excluded whatever its stored scope.
- Only a signed system context assigns a scope, in version order, for its
  own tenant's assets.
- A response with content carries `sources_used` and is signed for its
  request and nonce under the AI-to-backend secret.
"""

import hashlib
import hmac
import uuid

import pytest

from boundary.conftest import (
    A2B,
    SCOPE_ASSIGNMENTS,
    assign_scope,
    create_asset,
    create_job_for,
    jbytes,
    pdf_document,
    retrieving,
    system_context,
    to_ai,
    user_context,
    wait_for_status,
)

RETRIEVE = "/v1/ai/retrieve"
READY_TIMEOUT = 180


@pytest.fixture(scope="module")
def ready_asset(backend, tenant_a) -> tuple[str, str]:
    """A ready document of tenant A's that no other test assigns a scope."""
    marker = uuid.uuid4().hex
    asset = create_asset(backend, tenant_a, pdf_document(marker))
    job = create_job_for(backend, tenant_a, asset)
    final = wait_for_status(backend, tenant_a, job["id"], {"ready", "failed"}, timeout=READY_TIMEOUT)
    assert final["status"] == "ready", final
    return asset["id"], marker


def retrieve(ai, tenant, marker: str, denied: tuple[str, ...] = ()):
    member = tenant.members["student"]
    body = {**retrieving({"query": f"Reference {marker} charge"}), "denied_assets": sorted(denied)}
    raw = jbytes(body)
    context = user_context(tenant.tenant_id, member.user_id, ["ai.use"], membership_id=member.membership_id, role="student")
    headers = to_ai("POST", RETRIEVE, raw, context)
    response = ai.post(RETRIEVE, content=raw, headers=headers)
    assert response.status_code == 200, response.text
    return response, body, headers


def served(ai, tenant, asset_id: str, marker: str, denied: tuple[str, ...] = ()) -> bool:
    response, _, _ = retrieve(ai, tenant, marker, denied)
    payload = response.json()
    in_data = any(r["provenance"]["source_uri"] == f"asset:{asset_id}" for r in payload["data"])
    in_sources = any(s["asset_id"] == asset_id for s in payload["sources_used"])
    assert in_data == in_sources, payload  # what was served is exactly what is reported
    return in_data


def test_m3d_a_document_is_served_only_while_institutional_and_not_denied(ai, tenant_a, ready_asset):
    asset_id, marker = ready_asset
    tenant = tenant_a.tenant_id
    assert not served(ai, tenant_a, asset_id, marker)  # ready, but unknown

    assign_scope(ai, tenant, asset_id, "personal", version=1)
    assert not served(ai, tenant_a, asset_id, marker)

    assert assign_scope(ai, tenant, asset_id, "institutional", version=2)["scope"] == "institutional"
    assert served(ai, tenant_a, asset_id, marker)
    # Lowered by the backend and not yet acknowledged: denied at once.
    assert not served(ai, tenant_a, asset_id, marker, denied=(asset_id,))

    # A late, older assignment changes nothing and is acknowledged.
    stale = assign_scope(ai, tenant, asset_id, "unknown", version=1)
    assert (stale["scope"], stale["version"]) == ("institutional", 2)
    assert served(ai, tenant_a, asset_id, marker)

    assign_scope(ai, tenant, asset_id, "unknown", version=3)
    assert not served(ai, tenant_a, asset_id, marker)


def test_m3d_only_the_backends_system_context_assigns_a_scope(ai, tenant_a, tenant_b, ready_asset):
    asset_id, _ = ready_asset
    raw = jbytes({"asset_id": asset_id, "scope": "institutional", "version": 99})
    staff = user_context(tenant_a.tenant_id, str(uuid.uuid4()), ["content.job.manage", "content.asset.manage"])

    unsigned = ai.post(SCOPE_ASSIGNMENTS, content=raw, headers={"Content-Type": "application/json"})
    as_user = ai.post(SCOPE_ASSIGNMENTS, content=raw, headers=to_ai("POST", SCOPE_ASSIGNMENTS, raw, staff))
    other_tenant = ai.post(
        SCOPE_ASSIGNMENTS, content=raw, headers=to_ai("POST", SCOPE_ASSIGNMENTS, raw, system_context(tenant_b.tenant_id))
    )
    naming = jbytes({"asset_id": asset_id, "scope": "institutional", "version": 99, "tenant_id": tenant_b.tenant_id})
    named = ai.post(
        SCOPE_ASSIGNMENTS, content=naming, headers=to_ai("POST", SCOPE_ASSIGNMENTS, naming, system_context(tenant_a.tenant_id))
    )
    assert (unsigned.status_code, as_user.status_code, other_tenant.status_code, named.status_code) == (401, 403, 409, 422)


@pytest.mark.parametrize("missing", ["denied_assets", "response_nonce"])
def test_m3d_a_retrieving_call_without_its_denial_list_or_nonce_is_refused(ai, tenant_a, missing):
    member = tenant_a.members["student"]
    body = retrieving({"query": "charge"})
    del body[missing]
    raw = jbytes(body)
    context = user_context(tenant_a.tenant_id, member.user_id, ["ai.use"], membership_id=member.membership_id, role="student")
    assert ai.post(RETRIEVE, content=raw, headers=to_ai("POST", RETRIEVE, raw, context)).status_code == 422


def test_m3d_a_response_is_signed_for_its_request_and_nonce(ai, tenant_a, ready_asset):
    _, marker = ready_asset
    response, body, headers = retrieve(ai, tenant_a, marker)
    timestamp = response.headers["X-BUILD-Response-Timestamp"]
    canonical = "\n".join(
        (
            "v1",
            "response",
            "ai-service",
            headers["X-BUILD-Request-ID"],
            body["response_nonce"],
            timestamp,
            hashlib.sha256(response.content).hexdigest(),
        )
    ).encode()
    expected = "v1=" + hmac.new(A2B.encode(), canonical, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(response.headers["X-BUILD-Response-Signature"], expected)
    assert isinstance(response.json()["sources_used"], list)


@pytest.mark.parametrize("size,status", [(1000, 200), (1001, 422)])
def test_m3d_the_shared_denial_limit_is_the_same_on_both_sides(ai, tenant_a, size, status):
    # The backend's gateway never sends more than 1,000; the AI service refuses more.
    member = tenant_a.members["student"]
    body = {**retrieving({"query": "charge"}), "denied_assets": [str(uuid.uuid4()) for _ in range(size)]}
    raw = jbytes(body)
    context = user_context(tenant_a.tenant_id, member.user_id, ["ai.use"], membership_id=member.membership_id, role="student")
    assert ai.post(RETRIEVE, content=raw, headers=to_ai("POST", RETRIEVE, raw, context)).status_code == status

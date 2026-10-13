"""Signed AI-service -> backend callbacks through the real application (M3-07).

The callback route sits behind ServiceAuthMiddleware with a real Redis
replay store (TEST_REDIS_URL). Requests are signed the way AI-service signs
them: BUILD Service Signature v1, AI_TO_BACKEND_SECRET, system context.
"""

import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.config import settings
from app.domain.content.gateway import AIServiceDispatchResult
from app.infrastructure.security.replay_store import RedisReplayStore
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    HEADER_CONTEXT,
    HEADER_REQUEST_ID,
    HEADER_SERVICE,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    Direction,
    ServiceKeys,
    canonical_context_bytes,
    canonical_request,
    compute_signature,
    encode_context,
    sha256_hex,
    sign_request,
)
from app.main import app
from tests.integration.assessment.test_attempt_api import headers as tenant_headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)

REDIS_URL = os.getenv("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")

PATH = "/content/ingestion/callbacks"
UNIFORM_401 = {"error": "invalid service authentication"}


@pytest.fixture(autouse=True)
def real_replay_store(monkeypatch):
    store = RedisReplayStore.from_url(REDIS_URL, timeout_seconds=2)
    monkeypatch.setattr(app.state, "service_replay_store", store, raising=False)
    yield store


def keys() -> ServiceKeys:
    return ServiceKeys(current=settings.ai_to_backend_secret or "")


def system_context(tenant_id: str) -> ServiceContext:
    return ServiceContext.for_system(tenant_id=tenant_id, correlation_id="corr-cb")


def signed(
    body: bytes,
    tenant_id: str,
    *,
    target: str = PATH,
    context: ServiceContext | None = None,
    key: ServiceKeys | None = None,
    direction: Direction = Direction.AI_TO_BACKEND,
    request_id: str | None = None,
) -> dict[str, str]:
    headers = sign_request(
        direction=direction,
        keys=key or keys(),
        method="POST",
        target=target,
        body=body,
        context=context or system_context(tenant_id),
        timestamp=int(time.time()),
        request_id=request_id,
    )
    return {**headers, "Content-Type": "application/json"}


# The evidence each stage must carry (M3-08 stage contract).
EVIDENCE = {
    "extracted": {"characters": 900, "pages": 3, "method": "native_text"},
    "chunked": {"chunks": 3},
    "indexed": {"indexed_chunks": 3, "index": "pgvector"},
}


def event(job: dict, event_type: str = "stage_progress", stage: str | None = "extracted", **extra) -> bytes:
    body = {
        "job_id": job["id"],
        "event_id": str(uuid4()),
        "event_type": event_type,
        "external_task_id": job["external_task_id"],
        "run_number": job["run_number"],
        "attempt_count": job["attempt_count"],
        "metrics": EVIDENCE.get(stage or "", {}),
        **extra,
    }
    if stage is not None:
        body["stage"] = stage
    return json.dumps(body).encode()


async def processing_job(client, monkeypatch) -> tuple[dict, str, dict]:
    """A tenant job dispatched to AI-service (gateway stubbed): status processing."""
    admin_id, token = await register_and_authenticate(client, f"cb-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    h = tenant_headers(token, slug)
    source_id = client.post(
        "/content/sources",
        json={
            "code": f"SRC_CB_{uuid4().hex[:6].upper()}",
            "name": "Callbacks",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=h,
    ).json()["data"]["id"]
    asset_id = client.post(
        f"/content/sources/{source_id}/assets",
        json={
            "file_name": "cb.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 10,
            "content_sha256": "7" * 64,
            "storage_uri": "s3://build-assets/cb.pdf",
        },
        headers=h,
    ).json()["data"]["id"]
    job_id = client.post(f"/content/assets/{asset_id}/jobs", json={"max_attempts": 3}, headers=h).json()["data"]["id"]

    async def accepted(self, job, asset, source, actor):
        return AIServiceDispatchResult(
            external_task_id=f"task_{job.id}_a{job.attempt_count}",  # fresh per dispatch
            accepted_at=datetime.now(timezone.utc),
            status="ACCEPTED",
        )

    monkeypatch.setattr(
        "app.infrastructure.content.ai_gateway.HttpAIServiceIngestionGateway.dispatch_ingestion_job",
        accepted,
    )
    job = client.post(f"/content/jobs/{job_id}/dispatch", headers=h).json()["data"]
    assert job["status"] == "processing"
    return job, tenant_id, h


def status_of(client, job: dict, h: dict) -> str:
    return client.get(f"/content/jobs/{job['id']}", headers=h).json()["data"]["status"]


# --- accepted -------------------------------------------------------------------------


async def test_signed_callbacks_drive_the_job_to_ready(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    for event_type, stage in [
        ("stage_progress", "extracted"),
        ("stage_progress", "chunked"),
        ("stage_progress", "indexed"),
        ("job_completed", None),
    ]:
        body = event(job, event_type, stage)
        resp = client.post(PATH, content=body, headers=signed(body, tenant_id))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["outcome"] == "applied"
        assert resp.json()["data"]["already_processed"] is False
    assert status_of(client, job, h) == "ready"


async def test_the_same_event_resent_with_a_new_signature_is_idempotent(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job)
    first = client.post(PATH, content=body, headers=signed(body, tenant_id))
    again = client.post(PATH, content=body, headers=signed(body, tenant_id))
    assert first.json()["data"]["already_processed"] is False
    assert again.status_code == 200
    assert again.json()["data"]["already_processed"] is True
    assert again.json()["data"]["outcome"] == "duplicate"
    assert status_of(client, job, h) == "extracted"


# --- replay (C9) ------------------------------------------------------------------------


async def test_an_exact_replay_is_refused(client, monkeypatch):
    job, tenant_id, _ = await processing_job(client, monkeypatch)
    body = event(job)
    headers = signed(body, tenant_id)
    assert client.post(PATH, content=body, headers=headers).status_code == 200
    replay = client.post(PATH, content=body, headers=headers)
    assert (replay.status_code, replay.json()) == (401, UNIFORM_401)


async def test_a_reused_request_id_with_a_new_signature_is_refused(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    rid = str(uuid4())
    first = event(job, stage="extracted")
    second = event(job, stage="chunked")
    assert client.post(PATH, content=first, headers=signed(first, tenant_id, request_id=rid)).status_code == 200
    resp = client.post(PATH, content=second, headers=signed(second, tenant_id, request_id=rid))
    assert resp.status_code == 401
    assert status_of(client, job, h) == "extracted"


async def test_a_forged_callback_does_not_burn_the_request_id(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, "job_failed", None, error_code="X", error_message="forged")
    headers = signed(body, tenant_id)
    forged = client.post(PATH, content=event(job, "job_failed", None), headers=headers)
    genuine = client.post(PATH, content=body, headers=headers)
    assert (forged.status_code, genuine.status_code) == (401, 200)
    assert status_of(client, job, h) == "failed"


async def test_replay_keys_are_scoped_by_receiver_and_sender(client, monkeypatch):
    job, tenant_id, _ = await processing_job(client, monkeypatch)
    rid = str(uuid4())
    # The same id already used towards AI-service does not block the backend.
    other_direction = RedisReplayStore.from_url(REDIS_URL, timeout_seconds=2)
    try:
        assert await other_direction.claim("ai-service", "build-backend", rid) is True
    finally:
        await other_direction.close()
    body = event(job)
    assert client.post(PATH, content=body, headers=signed(body, tenant_id, request_id=rid)).status_code == 200


# --- authentication (C3-C8, C10, C12) ---------------------------------------------------


def _resign(headers: dict[str, str], body: bytes, **fields) -> dict[str, str]:
    """Recompute a valid signature over changed fields (timestamp, request id)."""
    values = {
        "service": headers[HEADER_SERVICE],
        "method": "POST",
        "target": PATH,
        "timestamp": headers[HEADER_TIMESTAMP],
        "request_id": headers[HEADER_REQUEST_ID],
        "body_sha256": sha256_hex(body),
        "context_sha256": sha256_hex(canonical_context_bytes(json.loads(_decode(headers[HEADER_CONTEXT])))),
    }
    values.update(fields)
    return {**headers, HEADER_SIGNATURE: compute_signature(settings.ai_to_backend_secret or "", canonical_request(**values))}


def _decode(context_header: str) -> str:
    import base64

    return base64.urlsafe_b64decode(context_header + "=" * (-len(context_header) % 4)).decode()


@pytest.mark.parametrize(
    "tamper",
    [
        "body",
        "query",
        "timestamp",
        "request_id",
        "context_tenant",
        "missing_signature",
        "malformed_signature",
        "wrong_sender",
        "backend_to_ai_secret",
        "bearer_only",
        "legacy_hmac",
    ],
)
async def test_tampered_or_unsigned_callbacks_are_refused(client, monkeypatch, tamper):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, "job_failed", None, error_code="X", error_message="tampered")
    headers = signed(body, tenant_id)
    path = PATH
    if tamper == "body":
        body = body.replace(b'"X"', b'"Y"')
    elif tamper == "query":
        path = PATH + "?job=other"
    elif tamper == "timestamp":
        headers[HEADER_TIMESTAMP] = str(int(headers[HEADER_TIMESTAMP]) - 1)
    elif tamper == "request_id":
        headers[HEADER_REQUEST_ID] = str(uuid4())
    elif tamper == "context_tenant":
        headers[HEADER_CONTEXT] = encode_context(system_context(str(uuid4())).to_dict())
    elif tamper == "missing_signature":
        del headers[HEADER_SIGNATURE]
    elif tamper == "malformed_signature":
        headers[HEADER_SIGNATURE] = "v1=" + "Z" * 64
    elif tamper == "wrong_sender":
        headers = signed(body, tenant_id, direction=Direction.BACKEND_TO_AI)
    elif tamper == "backend_to_ai_secret":
        headers = signed(body, tenant_id, key=ServiceKeys(current=settings.backend_to_ai_secret or ""))
    elif tamper == "bearer_only":
        headers = {"Authorization": f"Bearer {settings.ai_to_backend_secret}", "Content-Type": "application/json"}
    elif tamper == "legacy_hmac":
        import hashlib
        import hmac

        digest = hmac.new((settings.ai_to_backend_secret or "").encode(), body, hashlib.sha256).hexdigest()
        headers = {"X-Build-Signature": f"sha256={digest}", "Content-Type": "application/json"}

    resp = client.post(path, content=body, headers=headers)
    assert (resp.status_code, resp.json()) == (401, UNIFORM_401)
    assert status_of(client, job, h) == "processing"


async def test_stale_timestamp_is_refused(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, "job_failed", None)
    headers = signed(body, tenant_id)
    stale = str(int(headers[HEADER_TIMESTAMP]) - 120)
    resp = client.post(PATH, content=body, headers=_resign(headers, body, timestamp=stale) | {HEADER_TIMESTAMP: stale})
    assert resp.status_code == 401
    assert status_of(client, job, h) == "processing"


# --- context ------------------------------------------------------------------------------


async def test_a_user_context_is_not_a_callback(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, "job_failed", None)
    user = ServiceContext.for_user(
        tenant_id=tenant_id,
        user_id=str(uuid4()),
        membership_id=str(uuid4()),
        role="admin",
        permissions=["content.job.manage"],
        correlation_id="corr-cb",
    )
    resp = client.post(PATH, content=body, headers=signed(body, tenant_id, context=user))
    assert resp.status_code == 403
    assert status_of(client, job, h) == "processing"


async def test_a_system_context_with_permissions_is_refused(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, "job_failed", None)
    headers = signed(body, tenant_id)
    bad = system_context(tenant_id).to_dict() | {"permissions": ["content.job.manage"]}
    headers[HEADER_CONTEXT] = encode_context(bad)
    headers = _resign(headers, body, context_sha256=sha256_hex(canonical_context_bytes(bad)))
    resp = client.post(PATH, content=body, headers=headers)
    assert (resp.status_code, resp.json()) == (401, UNIFORM_401)
    assert status_of(client, job, h) == "processing"


async def test_a_callback_for_another_tenants_job_is_404_and_changes_nothing(client, monkeypatch):
    job, tenant_a, h = await processing_job(client, monkeypatch)
    _, tenant_b, _ = await processing_job(client, monkeypatch)
    body = event(job, "job_failed", None)
    resp = client.post(PATH, content=body, headers=signed(body, tenant_b))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert status_of(client, job, h) == "processing"


async def test_a_callback_for_an_unknown_job_is_404(client, monkeypatch):
    job, tenant_id, _ = await processing_job(client, monkeypatch)
    body = event({**job, "id": f"cjob-{uuid4()}"})
    assert client.post(PATH, content=body, headers=signed(body, tenant_id)).status_code == 404


# --- payload ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "x"},
        {"user_id": "x"},
        {"role": "admin"},
        {"callback_url": "https://x"},
        {"unexpected": 1},
        {"event_type": "COMPLETED"},
        {"stage": "ready"},
        {"run_number": "one"},
        {"metrics": "not an object"},
        {"metrics": {"blob": "x" * (65 * 1024)}},
    ],
)
async def test_invalid_callback_bodies_are_422(client, monkeypatch, change):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = json.loads(event(job))
    body.update(change)
    raw = json.dumps(body).encode()
    resp = client.post(PATH, content=raw, headers=signed(raw, tenant_id))
    assert resp.status_code == 422, resp.text
    assert status_of(client, job, h) == "processing"


@pytest.mark.parametrize("field", ["external_task_id", "run_number", "attempt_count", "event_id"])
async def test_task_identity_fields_are_required(client, monkeypatch, field):
    job, tenant_id, _ = await processing_job(client, monkeypatch)
    body = json.loads(event(job))
    del body[field]
    raw = json.dumps(body).encode()
    assert client.post(PATH, content=raw, headers=signed(raw, tenant_id)).status_code == 422


async def test_an_oversized_body_is_413(client, monkeypatch):
    job, tenant_id, _ = await processing_job(client, monkeypatch)
    raw = b"{" + b" " * (1024 * 1024) + b"}"
    assert client.post(PATH, content=raw, headers=signed(raw, tenant_id)).status_code == 413


async def test_redis_unavailable_is_503(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    monkeypatch.setattr(
        app.state, "service_replay_store", RedisReplayStore.from_url("redis://127.0.0.1:1/0", timeout_seconds=0.5)
    )
    body = event(job, "job_failed", None)
    resp = client.post(PATH, content=body, headers=signed(body, tenant_id))
    assert resp.status_code == 503
    assert status_of(client, job, h) == "processing"


# --- M3-08: state machine outcomes over HTTP ---------------------------------------------


async def test_completion_before_indexing_is_409_and_not_consumed(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    done = event(job, "job_completed", None)
    early = client.post(PATH, content=done, headers=signed(done, tenant_id))
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "TRANSITION_NOT_ALLOWED"
    assert status_of(client, job, h) == "processing"

    for stage in ("extracted", "chunked", "indexed"):
        body = event(job, stage=stage)
        assert client.post(PATH, content=body, headers=signed(body, tenant_id)).status_code == 200
    # The same logical event was not consumed, so it now applies.
    late = client.post(PATH, content=done, headers=signed(done, tenant_id))
    assert (late.status_code, late.json()["data"]["outcome"]) == (200, "applied")
    assert status_of(client, job, h) == "ready"


async def test_a_skipped_stage_is_409(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, stage="indexed")
    resp = client.post(PATH, content=body, headers=signed(body, tenant_id))
    assert resp.status_code == 409
    assert status_of(client, job, h) == "processing"


async def test_missing_stage_evidence_is_422(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = event(job, stage="extracted", metrics={"pages": 3})
    resp = client.post(PATH, content=body, headers=signed(body, tenant_id))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_STAGE_EVIDENCE"
    assert status_of(client, job, h) == "processing"


async def test_a_reached_stage_with_a_new_event_id_is_superseded(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    for _ in range(2):
        body = event(job, stage="extracted")
        resp = client.post(PATH, content=body, headers=signed(body, tenant_id))
    assert resp.json()["data"]["outcome"] == "superseded"
    assert status_of(client, job, h) == "extracted"


async def test_events_for_another_attempt_are_stale(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    for other in ({"attempt_count": 2}, {"run_number": 2}, {"external_task_id": "task_other"}):
        body = event({**job, **other}, "job_failed", None)
        resp = client.post(PATH, content=body, headers=signed(body, tenant_id))
        assert (resp.status_code, resp.json()["data"]["outcome"]) == (200, "stale")
    assert status_of(client, job, h) == "processing"


async def test_failure_then_retry_then_success_on_the_new_attempt(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    failed = event(job, "job_failed", None, error_code="TIMEOUT", error_message="t", is_retryable=True)
    assert client.post(PATH, content=failed, headers=signed(failed, tenant_id)).status_code == 200
    assert status_of(client, job, h) == "failed"

    retry = client.post(f"/content/jobs/{job['id']}/retry", json={"delay_seconds": 1}, headers=h)
    assert retry.status_code == 200, retry.text
    assert (retry.json()["data"]["attempt_count"], retry.json()["data"]["external_task_id"]) == (2, None)
    early = client.post(f"/content/jobs/{job['id']}/dispatch", headers=h)
    assert (early.status_code, early.json()["error"]["code"]) == (409, "RETRY_NOT_DUE")

    time.sleep(1.1)
    second = client.post(f"/content/jobs/{job['id']}/dispatch", headers=h).json()["data"]
    assert (second["status"], second["attempt_count"]) == ("processing", 2)

    # The first task's own retry claims attempt 2; it is still the old task.
    old = event({**job, "attempt_count": 2}, "job_failed", None)
    assert client.post(PATH, content=old, headers=signed(old, tenant_id)).json()["data"]["outcome"] == "stale"

    for stage in ("extracted", "chunked", "indexed"):
        body = event(second, stage=stage)
        assert client.post(PATH, content=body, headers=signed(body, tenant_id)).status_code == 200
    done = event(second, "job_completed", None)
    assert client.post(PATH, content=done, headers=signed(done, tenant_id)).status_code == 200
    assert status_of(client, job, h) == "ready"


async def test_a_late_failure_after_ready_is_409(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    for stage in ("extracted", "chunked", "indexed"):
        body = event(job, stage=stage)
        client.post(PATH, content=body, headers=signed(body, tenant_id))
    done = event(job, "job_completed", None)
    client.post(PATH, content=done, headers=signed(done, tenant_id))
    late = event(job, "job_failed", None)
    resp = client.post(PATH, content=late, headers=signed(late, tenant_id))
    assert resp.status_code == 409
    assert status_of(client, job, h) == "ready"


async def test_reusing_an_event_id_for_different_content_is_409(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    body = json.loads(event(job, stage="extracted"))
    raw = json.dumps(body).encode()
    assert client.post(PATH, content=raw, headers=signed(raw, tenant_id)).status_code == 200
    forged = json.dumps({**body, "metrics": {**body["metrics"], "pages": 99}}).encode()
    resp = client.post(PATH, content=forged, headers=signed(forged, tenant_id))
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "EVENT_CONFLICT")
    reordered = json.dumps(dict(reversed(list(body.items())))).encode()
    again = client.post(PATH, content=reordered, headers=signed(reordered, tenant_id))
    assert again.json()["data"]["outcome"] == "duplicate"  # same meaning, other key order
    assert status_of(client, job, h) == "extracted"

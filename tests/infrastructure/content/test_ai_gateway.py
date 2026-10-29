import json

import httpx
import pytest

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AuthorityLevel,
    ContentSourceType,
    VisibilityScope,
)
from app.domain.content.gateway import IngestionDispatchActor
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.content.ai_gateway import (
    AIServiceGatewayError,
    HttpAIServiceIngestionGateway,
)
from app.infrastructure.security.service_context import ServiceContext
from app.infrastructure.security.service_signature import (
    Direction,
    ServiceAuthError,
    ServiceKeys,
    sha256_hex,
    verify_request,
)

TENANT = "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c"
ACTOR = IngestionDispatchActor(
    tenant_id=TENANT,
    user_id="0b9d8c7a-6e5f-4a3b-8c2d-1e0f9a8b7c6d",
    membership_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    role="lecturer",
    permission="content.job.manage",
)
KEYS = ServiceKeys(current="test-backend-to-ai-secret-for-gateway-tests-0001")
DISPATCH_FIELDS = {
    "job_id",
    "asset_id",
    "source_id",
    "run_number",
    "attempt_count",
    "idempotency_key",
    "mime_type",
    "content_sha256",
    "file_size_bytes",
    "storage_uri",
    "correlation_id",
}


def _material(correlation_id: str | None = "corr-42"):
    source = ContentSource.create(
        code="CS101_SRC",
        name="CS101",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-1",
        created_by_email="u@example.com",
        tenant_id=TENANT,
    )
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="notes.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="a" * 64,
        storage_uri="s3://build/notes.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
        tenant_id=TENANT,
    )
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        tenant_id=TENANT,
        created_by="usr-1",
        correlation_id=correlation_id,
    )
    job.queue()
    return source, asset, job


def _gateway(handler, base_url: str = "http://ai-service.internal") -> HttpAIServiceIngestionGateway:
    return HttpAIServiceIngestionGateway(
        base_url=base_url,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        keys=KEYS,
    )


def _accepted(task_id: str = "task_9876") -> httpx.Response:
    return httpx.Response(202, json={"status": "ACCEPTED", "external_task_id": task_id})


@pytest.mark.asyncio
async def test_dispatch_is_signed_and_carries_the_tenant_only_in_the_context() -> None:
    source, asset, job = _material()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _accepted()

    result = await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert (result.external_task_id, result.status) == ("task_9876", "ACCEPTED")

    [request] = seen
    assert request.url.path == "/v1/ingest/dispatch"
    assert "authorization" not in request.headers  # no static Bearer key
    assert "x-tenant-id" not in request.headers

    # The receiving side of the protocol accepts exactly these bytes.
    verified = verify_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method="POST",
        target=request.url.raw_path.decode(),
        headers=dict(request.headers),
        body_sha256=sha256_hex(request.content),
        now=int(request.headers["x-build-timestamp"]),
    )
    assert verified.context == ServiceContext.for_user(
        tenant_id=TENANT,
        user_id=ACTOR.user_id,
        membership_id=ACTOR.membership_id,
        role="lecturer",
        permissions=["content.job.manage"],
        correlation_id="corr-42",
    )

    body = json.loads(request.content)
    assert set(body) == DISPATCH_FIELDS  # no tenant_id, callback_url or metadata
    assert body["idempotency_key"] == f"{job.id}-r1-a1"
    assert (body["job_id"], body["asset_id"], body["source_id"]) == (job.id, asset.id, source.id)


@pytest.mark.asyncio
async def test_a_tampered_dispatch_no_longer_verifies() -> None:
    source, asset, job = _material()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _accepted()

    await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    [request] = seen
    tampered = request.content.replace(job.id.encode(), b"cjob-someone-else")
    with pytest.raises(ServiceAuthError, match="signature mismatch"):
        verify_request(
            direction=Direction.BACKEND_TO_AI,
            keys=KEYS,
            method="POST",
            target=request.url.raw_path.decode(),
            headers=dict(request.headers),
            body_sha256=sha256_hex(tampered),
            now=int(request.headers["x-build-timestamp"]),
        )


@pytest.mark.asyncio
async def test_signed_target_includes_a_base_url_path_prefix() -> None:
    source, asset, job = _material()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _accepted()

    await _gateway(handler, base_url="http://gateway.internal/ai").dispatch_ingestion_job(
        job=job, asset=asset, source=source, actor=ACTOR
    )
    [request] = seen
    verify_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method="POST",
        target="/ai/v1/ingest/dispatch",
        headers=dict(request.headers),
        body_sha256=sha256_hex(request.content),
        now=int(request.headers["x-build-timestamp"]),
    )


@pytest.mark.asyncio
async def test_unusable_correlation_id_falls_back_to_the_job_id() -> None:
    source, asset, job = _material(correlation_id="has spaces/and slashes")
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _accepted()

    await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert json.loads(seen[0].content)["correlation_id"] == job.id


@pytest.mark.asyncio
async def test_dispatch_without_a_configured_secret_is_refused_before_sending(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "backend_to_ai_secret", None)
    source, asset, job = _material()
    sent: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return _accepted()

    gateway = HttpAIServiceIngestionGateway(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(AIServiceGatewayError) as exc_info:
        await gateway.dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert exc_info.value.error_code == "AI_SERVICE_NOT_CONFIGURED"
    assert sent == []


@pytest.mark.asyncio
async def test_acceptance_without_a_task_id_is_an_error() -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"status": "ACCEPTED"})

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert exc_info.value.error_code == "AI_SERVICE_BAD_RESPONSE"
    assert exc_info.value.outcome_uncertain is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 201, 202, 204])
async def test_successful_dispatch_requires_a_valid_accepted_response(status_code) -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        if status_code == 204:
            return httpx.Response(status_code)
        return httpx.Response(status_code, json={"status": "DUPLICATE", "external_task_id": "task_original"})

    if status_code == 204:
        with pytest.raises(AIServiceGatewayError) as exc_info:
            await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
        assert exc_info.value.outcome_uncertain is True
        return

    result = await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert (result.status, result.external_task_id) == ("DUPLICATE", "task_original")


@pytest.mark.asyncio
async def test_malformed_success_response_is_uncertain() -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, text="not json")

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert exc_info.value.error_code == "AI_SERVICE_BAD_RESPONSE"
    assert exc_info.value.outcome_uncertain is True


@pytest.mark.asyncio
async def test_transport_timeout_is_an_uncertain_dispatch() -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("response timed out", request=request)

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert exc_info.value.error_code == "AI_SERVICE_TRANSPORT_ERROR"
    assert exc_info.value.is_retryable is True
    assert exc_info.value.outcome_uncertain is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code", "retryable", "outcome_uncertain"),
    [
        (408, "AI_SERVICE_UNAVAILABLE", True, True),
        (429, "AI_SERVICE_UNAVAILABLE", True, True),
        (500, "AI_SERVICE_UNAVAILABLE", True, True),
        (502, "AI_SERVICE_UNAVAILABLE", True, True),
        (503, "AI_SERVICE_UNAVAILABLE", True, True),
        (504, "AI_SERVICE_UNAVAILABLE", True, True),
        (401, "AI_SERVICE_AUTH_ERROR", False, False),
        (403, "AI_SERVICE_AUTH_ERROR", False, False),
        (422, "AI_SERVICE_REJECTED", False, False),
        (404, "AI_SERVICE_OUTCOME_UNCERTAIN", True, True),
    ],
)
async def test_failure_classification(status_code, error_code, retryable, outcome_uncertain) -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, text="no")

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert (exc_info.value.error_code, exc_info.value.is_retryable, exc_info.value.outcome_uncertain) == (
        error_code,
        retryable,
        outcome_uncertain,
    )


@pytest.mark.asyncio
async def test_idempotency_conflict_is_a_definite_integrity_failure() -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "IDEMPOTENCY_CONFLICT: different work"})

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=ACTOR)
    assert exc_info.value.error_code == "AI_IDEMPOTENCY_CONFLICT"
    assert exc_info.value.is_retryable is False
    assert exc_info.value.outcome_uncertain is False


# --- M3-09: signed task status -----------------------------------------------------------


STATUS = {
    "external_task_id": "task_9876",
    "job_id": "job-1",
    "run_number": 1,
    "attempt_count": 2,
    "state": "failed",
    "events": [{"event_id": "e1", "event_type": "job_failed"}],
}


@pytest.mark.asyncio
async def test_task_status_is_a_signed_system_get_for_the_jobs_tenant() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=STATUS)

    result = await _gateway(handler).fetch_job_status("task_9876", TENANT, "corr-9")
    assert (result.job_id, result.attempt_count, result.state) == ("job-1", 2, "failed")
    assert result.events == STATUS["events"]

    [request] = seen
    assert (request.method, request.url.path, request.content) == (
        "GET",
        "/v1/ingest/tasks/task_9876",
        b"",
    )
    verified = verify_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method="GET",
        target=request.url.raw_path.decode(),
        headers=dict(request.headers),
        body_sha256=sha256_hex(b""),
        now=int(request.headers["x-build-timestamp"]),
    )
    assert verified.context == ServiceContext.for_system(tenant_id=TENANT, correlation_id="corr-9")


@pytest.mark.asyncio
async def test_task_ids_are_escaped_into_the_signed_path() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404)

    with pytest.raises(AIServiceGatewayError):
        await _gateway(handler).fetch_job_status("../dispatch?x=1", TENANT, "c")
    assert seen[0].url.raw_path == b"/v1/ingest/tasks/..%2Fdispatch%3Fx%3D1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error_code", "retryable"),
    [
        (httpx.Response(404), "AI_TASK_NOT_FOUND", False),
        (httpx.Response(401), "AI_SERVICE_AUTH_ERROR", False),
        (httpx.Response(503), "AI_SERVICE_POLL_FAILED", True),
        (httpx.Response(200, json={"state": "failed"}), "AI_SERVICE_BAD_RESPONSE", True),
        (httpx.Response(200, text="not json"), "AI_SERVICE_BAD_RESPONSE", True),
    ],
)
async def test_task_status_failures_are_classified(response, error_code, retryable) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).fetch_job_status("task_1", TENANT, "c")
    assert (exc_info.value.error_code, exc_info.value.is_retryable) == (error_code, retryable)


@pytest.mark.asyncio
async def test_task_status_without_a_secret_is_refused_before_sending(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "backend_to_ai_secret", None)
    sent: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=STATUS)

    gateway = HttpAIServiceIngestionGateway(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(AIServiceGatewayError) as exc_info:
        await gateway.fetch_job_status("task_1", TENANT, "c")
    assert exc_info.value.error_code == "AI_SERVICE_NOT_CONFIGURED"
    assert sent == []


# --- the worker's system dispatch (P3-6 §9) -------------------------------------------


@pytest.mark.asyncio
async def test_a_system_dispatch_is_signed_as_the_system_naming_the_jobs_tenant() -> None:
    from app.domain.content.gateway import SystemDispatchActor

    source, asset, job = _material()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _accepted()

    actor = SystemDispatchActor.for_job(job)
    await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=actor)

    [request] = seen
    verified = verify_request(
        direction=Direction.BACKEND_TO_AI,
        keys=KEYS,
        method="POST",
        target=request.url.raw_path.decode(),
        headers=dict(request.headers),
        body_sha256=sha256_hex(request.content),
        now=int(request.headers["x-build-timestamp"]),
    )
    # No user, no permissions: only the job's own tenant.
    assert verified.context == ServiceContext.for_system(tenant_id=TENANT, correlation_id="corr-42")
    body = json.loads(request.content)
    assert set(body) == DISPATCH_FIELDS
    # The attempt identity is the job's, exactly as a user dispatch sends it.
    assert (body["run_number"], body["attempt_count"]) == (job.run_number, job.attempt_count)
    assert body["idempotency_key"] == f"{job.id}-r{job.run_number}-a{job.attempt_count}"


@pytest.mark.asyncio
async def test_a_system_dispatch_can_never_name_another_tenant() -> None:
    from app.domain.content.gateway import JobTenantMissing, SystemDispatchActor

    source, asset, job = _material()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _accepted()

    other = SystemDispatchActor(tenant_id="11111111-2222-4333-8444-555555555555")
    with pytest.raises(JobTenantMissing):
        await _gateway(handler).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=other)
    assert seen == []

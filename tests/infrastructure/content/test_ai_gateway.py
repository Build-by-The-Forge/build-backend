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

    result = await _gateway(handler).dispatch_ingestion_job(
        job=job, asset=asset, source=source, actor=ACTOR
    )
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

    gateway = HttpAIServiceIngestionGateway(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
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
        await _gateway(handler).dispatch_ingestion_job(
            job=job, asset=asset, source=source, actor=ACTOR
        )
    assert exc_info.value.error_code == "AI_SERVICE_BAD_RESPONSE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code", "retryable"),
    [
        (503, "AI_SERVICE_UNAVAILABLE", True),
        (502, "AI_SERVICE_UNAVAILABLE", True),
        (401, "AI_SERVICE_AUTH_ERROR", False),
        (403, "AI_SERVICE_AUTH_ERROR", False),
        (422, "AI_SERVICE_REJECTED", False),
    ],
)
async def test_failure_classification(status_code, error_code, retryable) -> None:
    source, asset, job = _material()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, text="no")

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await _gateway(handler).dispatch_ingestion_job(
            job=job, asset=asset, source=source, actor=ACTOR
        )
    assert (exc_info.value.error_code, exc_info.value.is_retryable) == (error_code, retryable)

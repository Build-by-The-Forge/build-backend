from datetime import datetime, timezone
import pytest
import httpx

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AuthorityLevel,
    ContentSourceType,
    VisibilityScope,
)
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.content.ai_gateway import (
    AIServiceGatewayError,
    HttpAIServiceIngestionGateway,
    compute_webhook_signature,
    verify_webhook_signature,
)


def test_hmac_signature_generation_and_verification() -> None:
    payload = b'{"job_id":"cjob-123","event_type":"job_completed"}'
    secret = "super-secret-key-123"

    sig = compute_webhook_signature(payload, secret)
    assert sig.startswith("sha256=")

    # Valid verification
    assert verify_webhook_signature(payload, sig, secret) is True

    # Invalid secret
    assert verify_webhook_signature(payload, sig, "wrong-secret") is False

    # Tampered payload
    assert verify_webhook_signature(payload + b"tampered", sig, secret) is False

    # Missing signature or secret
    assert verify_webhook_signature(payload, None, secret) is False
    assert verify_webhook_signature(payload, sig, "") is False


@pytest.mark.asyncio
async def test_ai_gateway_dispatch_success() -> None:
    source = ContentSource.create(
        code="CS101_SRC",
        name="CS101",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
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
    )
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        created_by="usr-1",
        job_id="cjob-test-dispatch",
    )
    job.queue()

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/ingest/dispatch"
        assert "authorization" not in request.headers  # no static Bearer key
        assert "X-Idempotency-Key" in request.headers
        assert "X-Correlation-ID" in request.headers
        return httpx.Response(
            status_code=202,
            json={
                "status": "accepted",
                "task_id": "aitask-9876",
                "message": "Queued for processing",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    gateway = HttpAIServiceIngestionGateway(
        base_url="http://ai-service.internal",
        client=client,
    )

    result = await gateway.dispatch_ingestion_job(
        job=job,
        asset=asset,
        source=source,
        callback_url="https://api.build.internal/content/ingestion/callbacks",
    )

    assert result.external_task_id == "aitask-9876"
    assert result.status == "accepted"


@pytest.mark.asyncio
async def test_ai_gateway_transient_failure_classification() -> None:
    source = ContentSource.create(
        code="CS101_SRC",
        name="CS101",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
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
    )
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        created_by="usr-1",
    )
    job.queue()

    # 503 Service Unavailable
    async def mock_503_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, text="Service Unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_503_handler))
    gateway = HttpAIServiceIngestionGateway(client=client)

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await gateway.dispatch_ingestion_job(
            job=job,
            asset=asset,
            source=source,
            callback_url="/cb",
        )
    assert exc_info.value.is_retryable is True
    assert exc_info.value.error_code == "AI_SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_ai_gateway_permanent_failure_classification() -> None:
    source = ContentSource.create(
        code="CS101_SRC",
        name="CS101",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="corrupt.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="b" * 64,
        storage_uri="s3://build/corrupt.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        created_by="usr-1",
    )
    job.queue()

    # 422 Unprocessable Entity
    async def mock_422_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=422, text="Invalid payload format")

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_422_handler))
    gateway = HttpAIServiceIngestionGateway(client=client)

    with pytest.raises(AIServiceGatewayError) as exc_info:
        await gateway.dispatch_ingestion_job(
            job=job,
            asset=asset,
            source=source,
            callback_url="/cb",
        )
    assert exc_info.value.is_retryable is False
    assert exc_info.value.error_code == "AI_SERVICE_REJECTED"

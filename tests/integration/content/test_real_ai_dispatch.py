"""Backend -> AI-service dispatch against a real, separately running AI-service.

Skipped unless the two services share secrets for this run:

    REAL_AI_SERVICE_URL=http://127.0.0.1:8001
    REAL_BACKEND_TO_AI_SECRET=<the AI-service's BACKEND_TO_AI_SECRET>
    REAL_AI_TO_BACKEND_SECRET=<the AI-service's AI_TO_BACKEND_SECRET>

Nothing here is mocked: the backend's own gateway signs, httpx sends over a
socket, and AI-service verifies with its own implementation and real Redis.
"""

import json
import os
import time
from uuid import uuid4

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
from app.infrastructure.security.service_signature import Direction, ServiceKeys, sign_request

AI_URL = os.getenv("REAL_AI_SERVICE_URL")
B2A = os.getenv("REAL_BACKEND_TO_AI_SECRET")
A2B = os.getenv("REAL_AI_TO_BACKEND_SECRET")
pytestmark = pytest.mark.skipif(not (AI_URL and B2A and A2B), reason="real AI-service not configured")

TENANT_A = "6f1c2a7e-4b3d-4c8e-9a1f-2d3e4f5a6b7c"
TENANT_B = "9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a"


def actor(tenant_id: str = TENANT_A, permission: str = "content.job.manage"):
    return IngestionDispatchActor(
        tenant_id=tenant_id,
        user_id=str(uuid4()),
        membership_id=str(uuid4()),
        role="lecturer",
        permission=permission,
    )


def material(tenant_id: str = TENANT_A, job_id: str | None = None):
    source = ContentSource.create(
        code="REAL_SRC",
        name="Real",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-1",
        created_by_email="u@example.com",
        tenant_id=tenant_id,
    )
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="real.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=10,
        content_sha256="c" * 64,
        storage_uri="s3://build-assets/real.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
        tenant_id=tenant_id,
    )
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        tenant_id=tenant_id,
        created_by="usr-1",
        job_id=job_id,
    )
    job.queue()
    return source, asset, job


def gateway(secret: str | None = None) -> HttpAIServiceIngestionGateway:
    return HttpAIServiceIngestionGateway(base_url=AI_URL, keys=ServiceKeys(current=secret or B2A or ""))


@pytest.mark.asyncio
async def test_real_signed_dispatch_is_accepted() -> None:
    source, asset, job = material()
    result = await gateway().dispatch_ingestion_job(job=job, asset=asset, source=source, actor=actor())
    assert result.status == "ACCEPTED"
    assert result.external_task_id.startswith("task_")


@pytest.mark.asyncio
async def test_real_idempotency_follows_the_signed_tenant() -> None:
    job_id = f"cjob-{uuid4()}"

    async def dispatch(tenant_id: str):
        source, asset, job = material(tenant_id, job_id)
        return await gateway().dispatch_ingestion_job(job=job, asset=asset, source=source, actor=actor(tenant_id))

    first = await dispatch(TENANT_A)
    again = await dispatch(TENANT_A)
    other_tenant = await dispatch(TENANT_B)
    assert (again.status, again.external_task_id) == ("DUPLICATE", first.external_task_id)
    assert other_tenant.status == "ACCEPTED"
    assert other_tenant.external_task_id != first.external_task_id


@pytest.mark.asyncio
async def test_real_dispatch_signed_with_the_other_directions_secret_is_refused() -> None:
    source, asset, job = material()
    with pytest.raises(AIServiceGatewayError) as exc_info:
        await gateway(secret=A2B).dispatch_ingestion_job(job=job, asset=asset, source=source, actor=actor())
    assert exc_info.value.details == {"status_code": 401}


@pytest.mark.asyncio
async def test_real_dispatch_without_the_permission_is_refused() -> None:
    source, asset, job = material()
    with pytest.raises(AIServiceGatewayError) as exc_info:
        await gateway().dispatch_ingestion_job(job=job, asset=asset, source=source, actor=actor(permission="ai.use"))
    assert exc_info.value.details == {"status_code": 403}


def _raw_signed(body: dict, context: ServiceContext) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = sign_request(
        direction=Direction.BACKEND_TO_AI,
        keys=ServiceKeys(current=B2A or ""),
        method="POST",
        target="/v1/ingest/dispatch",
        body=raw,
        context=context,
        timestamp=int(time.time()),
    )
    return raw, {**headers, "Content-Type": "application/json"}


def _body(**extra) -> dict:
    return {
        "job_id": f"cjob-{uuid4()}",
        "asset_id": "asset-1",
        "source_id": "src-1",
        "run_number": 1,
        "attempt_count": 1,
        "idempotency_key": f"idem-{uuid4()}",
        "mime_type": "application/pdf",
        "content_sha256": "c" * 64,
        "storage_uri": "s3://build-assets/real.pdf",
        "correlation_id": "corr-real",
        **extra,
    }


def _context(tenant_id: str = TENANT_A) -> ServiceContext:
    return ServiceContext.for_user(
        tenant_id=tenant_id,
        user_id=str(uuid4()),
        membership_id=str(uuid4()),
        role="lecturer",
        permissions=["content.job.manage"],
        correlation_id="corr-real",
    )


def test_real_tampering_and_replay_are_refused() -> None:
    raw, headers = _raw_signed(_body(), _context())
    url = f"{AI_URL}/v1/ingest/dispatch"
    with httpx.Client(timeout=10) as http:
        tampered = http.post(url, content=raw.replace(b"asset-1", b"asset-2"), headers=headers)
        swapped = {**headers, "X-BUILD-Context": _raw_signed(_body(), _context(TENANT_B))[1]["X-BUILD-Context"]}
        tenant_swap = http.post(url, content=raw, headers=swapped)
        first = http.post(url, content=raw, headers=headers)
        replay = http.post(url, content=raw, headers=headers)
        query = http.post(url + "?tenant=other", content=raw, headers=headers)
    assert tampered.status_code == 401
    assert tenant_swap.status_code == 401
    assert first.status_code == 202
    assert replay.status_code == 401
    assert query.status_code == 401


@pytest.mark.parametrize(
    "extra",
    [{"tenant_id": TENANT_B}, {"callback_url": "https://attacker.example/x"}, {"user_id": str(uuid4())}],
)
def test_real_identity_fields_in_a_signed_body_are_rejected(extra) -> None:
    raw, headers = _raw_signed(_body(**extra), _context())
    with httpx.Client(timeout=10) as http:
        response = http.post(f"{AI_URL}/v1/ingest/dispatch", content=raw, headers=headers)
    assert response.status_code == 422


def test_real_bearer_and_unsigned_requests_are_refused() -> None:
    with httpx.Client(timeout=10) as http:
        for headers in ({"Authorization": f"Bearer {B2A}"}, {}):
            response = http.post(
                f"{AI_URL}/v1/ingest/dispatch",
                content=json.dumps(_body()).encode(),
                headers={**headers, "Content-Type": "application/json"},
            )
            assert response.status_code == 401


# --- M3-09: signed task status against the real AI-service -----------------------------


@pytest.mark.asyncio
async def test_real_task_status_answers_only_the_tasks_tenant() -> None:
    source, asset, job = material()
    accepted = await gateway().dispatch_ingestion_job(job=job, asset=asset, source=source, actor=actor())

    status = await gateway().fetch_job_status(accepted.external_task_id, TENANT_A, "corr-real")
    assert (status.external_task_id, status.job_id, status.run_number, status.attempt_count) == (
        accepted.external_task_id,
        job.id,
        job.run_number,
        job.attempt_count,
    )
    assert status.state in {"accepted", "running", "succeeded", "failed"}

    with pytest.raises(AIServiceGatewayError) as other_tenant:
        await gateway().fetch_job_status(accepted.external_task_id, TENANT_B, "corr-real")
    assert other_tenant.value.error_code == "AI_TASK_NOT_FOUND"

    with pytest.raises(AIServiceGatewayError) as unknown:
        await gateway().fetch_job_status(f"task_{uuid4().hex}", TENANT_A, "corr-real")
    assert unknown.value.error_code == "AI_TASK_NOT_FOUND"


def test_real_task_status_refuses_a_user_context_and_unsigned_calls() -> None:
    path = f"/v1/ingest/tasks/task_{uuid4().hex}"
    user = _context()
    headers = sign_request(
        direction=Direction.BACKEND_TO_AI,
        keys=ServiceKeys(current=B2A or ""),
        method="GET",
        target=path,
        body=b"",
        context=user,
        timestamp=int(time.time()),
    )
    with httpx.Client(timeout=10) as http:
        assert http.get(f"{AI_URL}{path}", headers=headers).status_code == 403
        assert http.get(f"{AI_URL}{path}").status_code == 401

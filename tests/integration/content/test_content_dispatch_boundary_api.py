"""The dispatch boundary through the real app (P3-1 PR 3b, design section
10): a row's storage_uri is never enough to reach the AI-service."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.domain.content.asset import ContentAsset
from app.domain.content.gateway import AIServiceDispatchResult
from app.domain.content.storage import ObjectStorageUnavailableError
from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.uploads import BUCKET, upload_asset

GATEWAY = "app.infrastructure.content.ai_gateway.HttpAIServiceIngestionGateway.dispatch_ingestion_job"


@pytest.fixture
def dispatched(monkeypatch) -> list[str]:
    """The jobs the AI gateway was asked to dispatch."""
    calls: list[str] = []

    async def dispatch(self, job, asset, source, actor):
        calls.append(job.id)
        return AIServiceDispatchResult(
            external_task_id=f"task-{job.id}", accepted_at=datetime.now(timezone.utc), status="accepted"
        )

    monkeypatch.setattr(GATEWAY, dispatch)
    return calls


@pytest.fixture
async def lecturer(client) -> dict:
    admin_id, _ = await register_and_authenticate(client, f"gate-admin-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    user_id, token = await register_and_authenticate(client, f"gate-lecturer-{uuid4()}@example.com")
    await add_membership(user_id, tenant_id, "lecturer")
    h = headers(token, slug)
    source = client.post(
        "/content/sources",
        headers=h,
        json={
            "code": f"GATE_{uuid4().hex[:8].upper()}",
            "name": "Gate notes",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert source.status_code == 201, source.text
    return {"tenant": tenant_id, "h": h, "source": source.json()["data"]["id"]}


def _queued_job(client, lecturer) -> tuple[dict, str]:
    asset = upload_asset(client, lecturer["source"], headers=lecturer["h"])
    assert asset.status_code == 201, asset.text
    job = client.post(f"/content/assets/{asset.json()['data']['id']}/jobs", json={"max_attempts": 3}, headers=lecturer["h"])
    assert job.status_code == 201, job.text
    return asset.json()["data"], job.json()["data"]["id"]


async def test_an_uploaded_asset_is_dispatched(client, lecturer, dispatched):
    _, job_id = _queued_job(client, lecturer)

    response = client.post(f"/content/jobs/{job_id}/dispatch", headers=lecturer["h"])

    assert response.status_code == 200, response.text
    assert dispatched == [job_id]


async def test_a_legacy_unmanaged_asset_cannot_be_queued(client, lecturer, dispatched):
    """A row written before PR 3b, pointing anywhere, gets no job."""
    asset = ContentAsset.create(
        source_id=lecturer["source"],
        tenant_id=lecturer["tenant"],
        file_name="legacy.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        content_sha256=uuid4().hex * 2,
        storage_uri=f"s3://{BUCKET}/elsewhere/legacy.pdf",
        created_by="legacy",
        created_by_email="legacy@build.internal",
    )
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await uow.assets.insert_asset(asset)

    create = client.post(f"/content/assets/{asset.id}/jobs", json={"max_attempts": 3}, headers=lecturer["h"])
    reprocess = client.post(f"/content/assets/{asset.id}/reprocess", json={}, headers=lecturer["h"])

    for response in (create, reprocess):
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "ASSET_NOT_IN_MANAGED_STORAGE"
    jobs = client.get(f"/content/assets/{asset.id}/jobs", headers=lecturer["h"]).json()["data"]
    assert jobs == []
    assert dispatched == []


@pytest.mark.parametrize("change", ["deleted", "replaced"])
async def test_a_missing_or_altered_object_is_refused_before_the_ai_service(
    client, lecturer, dispatched, managed_storage, change
):
    asset, job_id = _queued_job(client, lecturer)
    key = asset["storage_uri"].split("/", 3)[3]
    if change == "deleted":
        del managed_storage.objects[key]
    else:
        managed_storage.objects[key] = b"%PDF-1.7 different bytes"

    response = client.post(f"/content/jobs/{job_id}/dispatch", headers=lecturer["h"])

    expected = "ASSET_OBJECT_MISSING" if change == "deleted" else "ASSET_OBJECT_MISMATCH"
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == expected
    assert response.json()["data"]["status"] == "failed"
    assert dispatched == []


async def test_unavailable_storage_is_a_retryable_503(client, lecturer, dispatched, managed_storage, monkeypatch):
    _, job_id = _queued_job(client, lecturer)

    async def down(key):
        raise ObjectStorageUnavailableError("down")

    monkeypatch.setattr(managed_storage, "head", down)

    response = client.post(f"/content/jobs/{job_id}/dispatch", headers=lecturer["h"])

    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "5"
    assert response.json()["data"]["is_retryable"] is True
    assert dispatched == []

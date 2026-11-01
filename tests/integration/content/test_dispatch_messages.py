"""What a failed dispatch may tell a caller, now and later on the job's record."""

from uuid import uuid4

import pytest

from app.api.content import jobs
from app.infrastructure.content.ai_gateway import HttpAIServiceIngestionGateway
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.uploads import upload_asset

INTERNAL = "http://ai-service.internal:8000 secret-detail"


async def queued_job(client) -> tuple[dict[str, str], str]:
    user_id, token = await register_and_authenticate(client, f"dispatch-{uuid4()}@example.com")
    _, slug, _, _ = await seed_tenant_context(user_id, "admin")
    lecturer = headers(token, slug)
    source = client.post(
        "/content/sources",
        json={
            "code": f"SRC_{uuid4().hex[:6].upper()}",
            "name": "Messages",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=lecturer,
    )
    assert source.status_code == 201, source.text
    asset = upload_asset(client, source.json()["data"]["id"], headers=lecturer, name="messages.pdf")
    assert asset.status_code == 201, asset.text
    job = client.post(f"/content/assets/{asset.json()['data']['id']}/jobs", json={}, headers=lecturer)
    assert job.status_code == 201, job.text
    return lecturer, job.json()["data"]["id"]


@pytest.mark.asyncio
async def test_an_unexpected_dispatch_failure_names_no_internals(client, monkeypatch):
    lecturer, job_id = await queued_job(client)

    async def broken(**_):
        raise RuntimeError(INTERNAL)

    monkeypatch.setattr(jobs.service, "dispatch_job", broken)
    response = client.post(f"/content/jobs/{job_id}/dispatch", headers=lecturer)
    assert response.status_code == 502
    assert "secret-detail" not in response.text
    assert "ai-service.internal" not in response.text


@pytest.mark.asyncio
async def test_an_unexpected_gateway_failure_is_not_stored_on_the_job(client, monkeypatch):
    lecturer, job_id = await queued_job(client)

    async def broken(self, **_):
        raise RuntimeError(INTERNAL)

    monkeypatch.setattr(HttpAIServiceIngestionGateway, "dispatch_ingestion_job", broken)
    response = client.post(f"/content/jobs/{job_id}/dispatch", headers=lecturer)
    assert "secret-detail" not in response.text
    stored = client.get(f"/content/jobs/{job_id}", headers=lecturer)
    assert stored.status_code == 200, stored.text
    assert stored.json()["data"]["status"] == "failed"
    assert "secret-detail" not in stored.text
    assert "ai-service.internal" not in stored.text

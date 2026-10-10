"""POST /content/jobs/{id}/reconcile through the application (M3-09).

AI-service's signed status is replaced by a stub of the gateway method; the
real two-service path is exercised separately against a running AI-service.
"""

from uuid import uuid4

import pytest

from app.domain.content.gateway import AIServiceStatusResult
from app.infrastructure.content.ai_gateway import AIServiceGatewayError
from tests.integration.assessment.test_question_api import register_and_authenticate
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.test_signed_callbacks import processing_job, status_of

GATEWAY = "app.infrastructure.content.ai_gateway.HttpAIServiceIngestionGateway.fetch_job_status"


def stub_status(monkeypatch, make):
    calls: list[tuple] = []

    async def fetch(self, external_task_id, tenant_id, correlation_id):
        calls.append((external_task_id, tenant_id))
        return make()

    monkeypatch.setattr(GATEWAY, fetch)
    return calls


def failure_report(job: dict, **overrides) -> AIServiceStatusResult:
    fields = dict(
        external_task_id=job["external_task_id"],
        job_id=job["id"],
        run_number=job["run_number"],
        attempt_count=job["attempt_count"],
        state="failed",
        events=[
            {
                "event_id": str(uuid4()),
                "job_id": job["id"],
                "external_task_id": job["external_task_id"],
                "run_number": job["run_number"],
                "attempt_count": job["attempt_count"],
                "event_type": "job_failed",
                "error_code": "INGESTION_PIPELINE_UNAVAILABLE",
                "error_message": "no pipeline",
                "is_retryable": False,
            }
        ],
    )
    fields.update(overrides)
    return AIServiceStatusResult(**fields)


@pytest.mark.asyncio
async def test_reconcile_applies_an_undelivered_failure(client, monkeypatch):
    job, tenant_id, h = await processing_job(client, monkeypatch)
    report = failure_report(job)
    calls = stub_status(monkeypatch, lambda: report)

    resp = client.post(f"/content/jobs/{job['id']}/reconcile", headers=h)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "failed"
    assert resp.json()["data"]["error_code"] == "INGESTION_PIPELINE_UNAVAILABLE"
    assert resp.json()["meta"]["reconciled"] == [
        {"event_id": report.events[0]["event_id"], "outcome": "applied"}
    ]
    assert calls == [(job["external_task_id"], tenant_id)]


@pytest.mark.asyncio
async def test_reconcile_of_another_tenants_job_is_404(client, monkeypatch):
    job, _, _ = await processing_job(client, monkeypatch)
    _, _, other_headers = await processing_job(client, monkeypatch)
    calls = stub_status(monkeypatch, lambda: failure_report(job))
    resp = client.post(f"/content/jobs/{job['id']}/reconcile", headers=other_headers)
    assert resp.status_code == 404
    assert calls == []


@pytest.mark.asyncio
async def test_a_student_cannot_reconcile(client, monkeypatch):
    job, tenant_id, _ = await processing_job(client, monkeypatch)
    student_id, token = await register_and_authenticate(client, f"rec-stu-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    slug = client.get("/identity/memberships", headers={"Authorization": f"Bearer {token}"}).json()
    from tests.integration.assessment.test_attempt_api import headers as tenant_headers

    tenant_slug = next(m["tenant_slug"] for m in slug["data"] if m["tenant_id"] == tenant_id)
    resp = client.post(f"/content/jobs/{job['id']}/reconcile", headers=tenant_headers(token, tenant_slug))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reconcile_of_an_inactive_job_is_409(client, monkeypatch):
    job, _, h = await processing_job(client, monkeypatch)
    stub_status(monkeypatch, lambda: failure_report(job))
    assert client.post(f"/content/jobs/{job['id']}/reconcile", headers=h).status_code == 200
    again = client.post(f"/content/jobs/{job['id']}/reconcile", headers=h)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "TRANSITION_NOT_ALLOWED")


@pytest.mark.asyncio
async def test_a_report_on_another_task_is_502_and_changes_nothing(client, monkeypatch):
    job, _, h = await processing_job(client, monkeypatch)
    stub_status(monkeypatch, lambda: failure_report(job, external_task_id="task_other"))
    resp = client.post(f"/content/jobs/{job['id']}/reconcile", headers=h)
    assert (resp.status_code, resp.json()["error"]["code"]) == (502, "AI_STATUS_MISMATCH")
    assert status_of(client, job, h) == "processing"


@pytest.mark.asyncio
async def test_an_ai_service_failure_is_502_and_changes_nothing(client, monkeypatch):
    job, _, h = await processing_job(client, monkeypatch)

    def unavailable():
        raise AIServiceGatewayError("down", error_code="AI_SERVICE_POLL_FAILED", is_retryable=True)

    stub_status(monkeypatch, unavailable)
    resp = client.post(f"/content/jobs/{job['id']}/reconcile", headers=h)
    assert (resp.status_code, resp.json()["error"]["code"]) == (502, "AI_SERVICE_POLL_FAILED")
    assert status_of(client, job, h) == "processing"

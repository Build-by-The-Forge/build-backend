"""POST /content/jobs/{id}/reconcile through the application (M3-09).

AI-service's signed status is replaced by a stub of the gateway method; the
real two-service path is exercised separately against a running AI-service.
"""

import logging
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.domain.content.gateway import AIServiceStatusResult
from app.infrastructure.content.ai_gateway import AIServiceGatewayError
from app.infrastructure.db.models.content import ContentAssetModel, ContentIngestionJobModel
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
    assert resp.json()["meta"]["reconciled"] == [{"event_id": report.events[0]["event_id"], "outcome": "applied"}]
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


# --- a report's text doesn't reach the job by this path either ---------------------------

LEAK = "http://ai-service.internal:8000/v1 password=hunter2 sk-provider-key"


def assert_no_leak(text: str) -> None:
    for fragment in ("ai-service.internal", "hunter2", "sk-provider-key"):
        assert fragment not in text


@pytest.mark.asyncio
async def test_a_reconciled_failure_stores_and_returns_nothing_free_form(client, monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    job, _, h = await processing_job(client, monkeypatch)
    report = failure_report(job)
    report.events[0].update(error_message=LEAK, details={"provider_response": LEAK})
    stub_status(monkeypatch, lambda: report)

    assert client.post(f"/content/jobs/{job['id']}/reconcile", headers=h).status_code == 200

    read = client.get(f"/content/jobs/{job['id']}", headers=h)
    assert read.json()["data"]["error_code"] == "INGESTION_PIPELINE_UNAVAILABLE"
    assert_no_leak(read.text)
    # Secret-looking values are redacted from the log too.
    assert "ai-service.internal" in caplog.text
    assert "hunter2" not in caplog.text


@pytest.mark.asyncio
async def test_text_stored_before_the_filter_is_clean_on_the_way_out(client, monkeypatch):
    job, _, h = await processing_job(client, monkeypatch)
    old_attempt = {"attempt": 1, "error_code": "OCR_PAGE_FAILED", "error_message": LEAK, "error_details": {"url": LEAK}}
    async with SessionLocal() as db:
        await db.execute(
            update(ContentIngestionJobModel)
            .where(ContentIngestionJobModel.id == job["id"])
            .values(
                error_code="OCR_PAGE_FAILED",
                error_message=LEAK,
                error_details={"url": LEAK},
                metrics={"debug": LEAK, "characters": 5},
                attempt_history=[old_attempt],
            )
        )
        await db.execute(
            update(ContentAssetModel)
            .where(ContentAssetModel.id == job["asset_id"])
            .values(metadata_json={"error_code": "OCR_PAGE_FAILED", "error_message": LEAK})
        )
        await db.commit()

    read = client.get(f"/content/jobs/{job['id']}", headers=h)
    assert read.status_code == 200
    assert read.json()["data"]["metrics"] == {"characters": 5}
    assert_no_leak(read.text)
    asset = client.get(f"/content/assets/{job['asset_id']}", headers=h)
    assert asset.status_code == 200
    assert_no_leak(asset.text)

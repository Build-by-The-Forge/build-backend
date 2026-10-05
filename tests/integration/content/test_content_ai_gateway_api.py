from uuid import uuid4
import json
import pytest

from app.core.config import settings
from app.infrastructure.content.ai_gateway import compute_webhook_signature
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)
from tests.integration.content.test_content_source_api import add_membership


@pytest.mark.asyncio
async def test_ai_gateway_api_dispatch_and_hmac_callbacks(client, monkeypatch) -> None:
    # 1. Admin setup (Tenant A)
    admin_id, admin_token = await register_and_authenticate(
        client, f"aigate-admin-{uuid4()}@example.com"
    )
    tenant_a_id, tenant_a_slug, _, _ = await seed_tenant_context(admin_id, "admin")

    # 2. Lecturer setup (Tenant A)
    lecturer_a_id, lecturer_a_token = await register_and_authenticate(
        client, f"aigate-lecturer-a-{uuid4()}@example.com"
    )
    await add_membership(lecturer_a_id, tenant_a_id, "lecturer")
    lecturer_headers = headers(lecturer_a_token, tenant_a_slug)

    # 3. Student setup (Tenant A)
    student_a_id, student_a_token = await register_and_authenticate(
        client, f"aigate-student-a-{uuid4()}@example.com"
    )
    await add_membership(student_a_id, tenant_a_id, "student")
    student_headers = headers(student_a_token, tenant_a_slug)

    # 4. Create Source & Asset
    source_res = client.post(
        "/content/sources",
        json={
            "code": f"SRC_AI_{uuid4().hex[:6].upper()}",
            "name": "AI Gateway Course Materials",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=lecturer_headers,
    )
    assert source_res.status_code == 201, source_res.text
    source_id = source_res.json()["data"]["id"]

    asset_res = client.post(
        f"/content/sources/{source_id}/assets",
        json={
            "file_name": "ai_course.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 10240,
            "content_sha256": "8" * 64,
            "storage_uri": "s3://build-assets/ai_course.pdf",
        },
        headers=lecturer_headers,
    )
    assert asset_res.status_code == 201, asset_res.text
    asset_id = asset_res.json()["data"]["id"]

    # 5. Trigger Ingestion Job
    job_res = client.post(
        f"/content/assets/{asset_id}/jobs",
        json={"max_attempts": 3},
        headers=lecturer_headers,
    )
    assert job_res.status_code == 201, job_res.text
    job_id = job_res.json()["data"]["id"]

    # A. Student attempts dispatch -> 403 Forbidden
    stu_disp = client.post(
        f"/content/jobs/{job_id}/dispatch",
        headers=student_headers,
    )
    assert stu_disp.status_code == 403

    # B. Mock Gateway dispatch call for Lecturer
    from app.domain.content.gateway import AIServiceDispatchResult
    from datetime import datetime, timezone

    actors = []

    async def mock_dispatch(self, job, asset, source, actor):
        actors.append(actor)
        return AIServiceDispatchResult(
            external_task_id=f"aitask-mock-{job.id}",
            accepted_at=datetime.now(timezone.utc),
            status="accepted",
        )

    monkeypatch.setattr(
        "app.infrastructure.content.ai_gateway.HttpAIServiceIngestionGateway.dispatch_ingestion_job",
        mock_dispatch,
    )

    # C. Lecturer dispatches job to AI Service
    disp_res = client.post(
        f"/content/jobs/{job_id}/dispatch",
        headers=lecturer_headers,
    )
    assert disp_res.status_code == 200, disp_res.text
    disp_data = disp_res.json()["data"]
    assert disp_data["status"] == "processing"
    assert disp_data["external_task_id"] == f"aitask-mock-{job_id}"
    # The signed context is built from the database-verified tenant context
    # and carries only the permission checked for this operation (C15, E.6).
    [actor] = actors
    assert (actor.tenant_id, actor.user_id, actor.role, actor.permission) == (
        tenant_a_id,
        lecturer_a_id,
        "lecturer",
        "content.job.manage",
    )

    # D. Webhook callback without signature -> 401 Unauthorized
    cb_payload_1 = {
        "job_id": job_id,
        "event_id": "evt-ai-1",
        "event_type": "stage_progress",
        "stage": "extracted",
        "external_task_id": f"aitask-mock-{job_id}",
        "run_number": 1,
        "attempt_count": 1,
        "metrics": {"pages_extracted": 25},
    }
    raw_cb_1 = json.dumps(cb_payload_1).encode("utf-8")

    unauth_cb = client.post(
        "/content/ingestion/callbacks",
        content=raw_cb_1,
        headers={"Content-Type": "application/json"},
    )
    assert unauth_cb.status_code == 401

    # E. Webhook callback with valid HMAC signature -> 200 OK (EXTRACTED)
    sig_1 = compute_webhook_signature(raw_cb_1, settings.ai_to_backend_secret)
    auth_cb_1 = client.post(
        "/content/ingestion/callbacks",
        content=raw_cb_1,
        headers={"Content-Type": "application/json", "X-Build-Signature": sig_1},
    )
    assert auth_cb_1.status_code == 200, auth_cb_1.text
    assert auth_cb_1.json()["data"]["already_processed"] is False

    # F. Duplicate callback with same event_id -> 200 OK with already_processed=True
    dup_cb = client.post(
        "/content/ingestion/callbacks",
        content=raw_cb_1,
        headers={"Content-Type": "application/json", "X-Build-Signature": sig_1},
    )
    assert dup_cb.status_code == 200
    assert dup_cb.json()["data"]["already_processed"] is True

    # G. Webhook callback: CHUNKED -> INDEXED -> COMPLETED
    for stage, ev_type in [
        ("chunked", "stage_progress"),
        ("indexed", "stage_progress"),
        ("ready", "job_completed"),
    ]:
        cb_payload = {
            "job_id": job_id,
            "event_id": f"evt-ai-{stage}",
            "event_type": ev_type,
            "stage": stage if ev_type != "job_completed" else None,
            "external_task_id": f"aitask-mock-{job_id}",
            "run_number": 1,
            "attempt_count": 1,
            "metrics": {"duration_ms": 500},
        }
        raw_cb = json.dumps(cb_payload).encode("utf-8")
        sig = compute_webhook_signature(raw_cb, settings.ai_to_backend_secret)
        res = client.post(
            "/content/ingestion/callbacks",
            content=raw_cb,
            headers={"Content-Type": "application/json", "X-Build-Signature": sig},
        )
        assert res.status_code == 200, res.text

    # H. Verify final asset status projection is READY
    asset_check = client.get(
        f"/content/assets/{asset_id}",
        headers=lecturer_headers,
    )
    assert asset_check.status_code == 200
    assert asset_check.json()["data"]["ingestion_status"] == "ready"


@pytest.mark.asyncio
async def test_failed_dispatch_is_persisted_and_reported(client, monkeypatch) -> None:
    from app.infrastructure.content.ai_gateway import AIServiceGatewayError

    admin_id, admin_token = await register_and_authenticate(
        client, f"aigate-fail-{uuid4()}@example.com"
    )
    _, tenant_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, tenant_slug)
    source_id = client.post(
        "/content/sources",
        json={
            "code": f"SRC_AF_{uuid4().hex[:6].upper()}",
            "name": "Fail path",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=admin_headers,
    ).json()["data"]["id"]
    asset_id = client.post(
        f"/content/sources/{source_id}/assets",
        json={
            "file_name": "f.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 10,
            "content_sha256": "9" * 64,
            "storage_uri": "s3://build-assets/f.pdf",
        },
        headers=admin_headers,
    ).json()["data"]["id"]
    job_id = client.post(
        f"/content/assets/{asset_id}/jobs", json={"max_attempts": 3}, headers=admin_headers
    ).json()["data"]["id"]

    async def failing_dispatch(self, job, asset, source, actor):
        raise AIServiceGatewayError(
            "AI Service transient error (HTTP 503)",
            error_code="AI_SERVICE_UNAVAILABLE",
            is_retryable=True,
        )

    monkeypatch.setattr(
        "app.infrastructure.content.ai_gateway.HttpAIServiceIngestionGateway.dispatch_ingestion_job",
        failing_dispatch,
    )

    resp = client.post(f"/content/jobs/{job_id}/dispatch", headers=admin_headers)
    assert resp.status_code == 502, resp.text
    assert resp.json()["error"]["code"] == "AI_SERVICE_UNAVAILABLE"

    # The failure survived the request: before M3-06 it was rolled back.
    stored = client.get(f"/content/jobs/{job_id}", headers=admin_headers).json()["data"]
    assert (stored["status"], stored["error_code"], stored["is_retryable"]) == (
        "failed",
        "AI_SERVICE_UNAVAILABLE",
        True,
    )
    # ... so the retry business operation is now possible.
    retry = client.post(
        f"/content/jobs/{job_id}/retry", json={"delay_seconds": 1}, headers=admin_headers
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["data"]["status"] == "queued"

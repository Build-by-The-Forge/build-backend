from uuid import uuid4

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.infrastructure.db.models.content import ContentIngestionJobModel
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.uploads import upload_asset


@pytest.mark.asyncio
async def test_content_job_api_and_rbac(client) -> None:
    # 1. Admin setup (Tenant A)
    admin_id, admin_token = await register_and_authenticate(client, f"job-admin-{uuid4()}@example.com")
    tenant_a_id, tenant_a_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, tenant_a_slug)

    # 2. Lecturer setup (Tenant A)
    lecturer_a_id, lecturer_a_token = await register_and_authenticate(client, f"job-lecturer-a-{uuid4()}@example.com")
    await add_membership(lecturer_a_id, tenant_a_id, "lecturer")
    lecturer_headers = headers(lecturer_a_token, tenant_a_slug)

    # 3. Student setup (Tenant A)
    student_a_id, student_a_token = await register_and_authenticate(client, f"job-student-a-{uuid4()}@example.com")
    await add_membership(student_a_id, tenant_a_id, "student")
    student_headers = headers(student_a_token, tenant_a_slug)

    # 4. Create Source
    source_res = client.post(
        "/content/sources",
        json={
            "code": f"SRC_JOB_{uuid4().hex[:6].upper()}",
            "name": "Job Processing Materials",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=lecturer_headers,
    )
    assert source_res.status_code == 201, source_res.text
    source_id = source_res.json()["data"]["id"]

    # 5. Create Asset
    asset_res = upload_asset(client, source_id, headers=lecturer_headers, name="syllabus.pdf")
    assert asset_res.status_code == 201, asset_res.text
    asset_id = asset_res.json()["data"]["id"]

    # A. Student attempts to trigger job -> 403 Forbidden
    stu_res = client.post(
        f"/content/assets/{asset_id}/jobs",
        json={"max_attempts": 3},
        headers=student_headers,
    )
    assert stu_res.status_code == 403

    # B. Lecturer triggers job -> 201 Created
    trigger_res = client.post(
        f"/content/assets/{asset_id}/jobs",
        json={"max_attempts": 3, "correlation_id": "test-corr-1"},
        headers=lecturer_headers,
    )
    assert trigger_res.status_code == 201, trigger_res.text
    job_data = trigger_res.json()["data"]
    job_id = job_data["id"]
    assert job_data["status"] == "queued"
    assert job_data["run_number"] == 1

    # C. Get job details -> 200 OK
    get_res = client.get(
        f"/content/jobs/{job_id}",
        headers=lecturer_headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == job_id

    # D. Processing transitions are not part of the public API (M3, N-3):
    #    only verified AI-service callbacks move a job through them.
    for path in ("start", "progress", "complete", "fail"):
        resp = client.post(f"/content/jobs/{job_id}/{path}", json={}, headers=admin_headers)
        assert resp.status_code in (404, 405), (path, resp.status_code)
    assert client.get(f"/content/jobs/{job_id}", headers=lecturer_headers).json()["data"]["status"] == "queued"

    # E. Another tenant's admin can neither see nor operate tenant A's job or asset (M3, N-1).
    other_admin_id, other_admin_token = await register_and_authenticate(client, f"job-admin-b-{uuid4()}@example.com")
    _, tenant_b_slug, _, _ = await seed_tenant_context(other_admin_id, "admin")
    other_headers = headers(other_admin_token, tenant_b_slug)
    cross = [
        client.get(f"/content/jobs/{job_id}", headers=other_headers),
        client.post(f"/content/jobs/{job_id}/dispatch", headers=other_headers),
        client.post(f"/content/jobs/{job_id}/retry", json={"delay_seconds": 1}, headers=other_headers),
        client.post(f"/content/assets/{asset_id}/reprocess", json={}, headers=other_headers),
        client.post(f"/content/assets/{asset_id}/jobs", json={"max_attempts": 3}, headers=other_headers),
    ]
    assert [r.status_code for r in cross] == [404] * len(cross), [(r.status_code, r.text) for r in cross]
    assert client.get(f"/content/jobs/{job_id}", headers=lecturer_headers).json()["data"]["status"] == "queued"

    # F. Retry and reprocess are business operations. Simulate AI-service having
    #    reported a retryable failure (in M3 only verified callbacks do this).
    async def mark_failed() -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(ContentIngestionJobModel)
                .where(ContentIngestionJobModel.id == job_id)
                .values(status="failed", is_retryable=True, error_code="TIMEOUT", error_message="AI timeout")
            )
            await session.commit()

    await mark_failed()

    reprocess_res = client.post(
        f"/content/assets/{asset_id}/reprocess",
        json={"correlation_id": "test-corr-reprocess"},
        headers=admin_headers,
    )
    assert reprocess_res.status_code == 201, reprocess_res.text
    run2 = reprocess_res.json()["data"]
    assert (run2["run_number"], run2["status"]) == (2, "queued")
    assert run2["id"] != job_id

    retry_res = client.post(f"/content/jobs/{job_id}/retry", json={"delay_seconds": 1}, headers=admin_headers)
    assert retry_res.status_code == 200, retry_res.text
    assert (retry_res.json()["data"]["status"], retry_res.json()["data"]["attempt_count"]) == ("queued", 2)

    # G. Students cannot operate jobs at all.
    assert client.post(f"/content/jobs/{job_id}/retry", json={"delay_seconds": 1}, headers=student_headers).status_code == 403

    list_res = client.get(f"/content/assets/{asset_id}/jobs", headers=lecturer_headers)
    assert list_res.status_code == 200
    assert list_res.json()["meta"]["total"] == 2

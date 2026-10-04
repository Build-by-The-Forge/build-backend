from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)
from tests.integration.content.test_content_source_api import add_membership


@pytest.mark.asyncio
async def test_content_job_api_and_rbac(client) -> None:
    # 1. Admin setup (Tenant A)
    admin_id, admin_token = await register_and_authenticate(
        client, f"job-admin-{uuid4()}@example.com"
    )
    tenant_a_id, tenant_a_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, tenant_a_slug)

    # 2. Lecturer setup (Tenant A)
    lecturer_a_id, lecturer_a_token = await register_and_authenticate(
        client, f"job-lecturer-a-{uuid4()}@example.com"
    )
    await add_membership(lecturer_a_id, tenant_a_id, "lecturer")
    lecturer_headers = headers(lecturer_a_token, tenant_a_slug)

    # 3. Student setup (Tenant A)
    student_a_id, student_a_token = await register_and_authenticate(
        client, f"job-student-a-{uuid4()}@example.com"
    )
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
    sha = "f" * 64
    asset_res = client.post(
        f"/content/sources/{source_id}/assets",
        json={
            "file_name": "syllabus.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 10240,
            "content_sha256": sha,
            "storage_uri": "s3://build-assets/syllabus.pdf",
        },
        headers=lecturer_headers,
    )
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

    # D. Start job -> processing
    start_res = client.post(
        f"/content/jobs/{job_id}/start?stage=parsing",
        headers=lecturer_headers,
    )
    assert start_res.status_code == 200
    assert start_res.json()["data"]["status"] == "processing"

    # E. Progress to extracted
    prog_res = client.post(
        f"/content/jobs/{job_id}/progress",
        json={"target_stage": "extracted", "metrics": {"pages": 15}},
        headers=lecturer_headers,
    )
    assert prog_res.status_code == 200
    assert prog_res.json()["data"]["status"] == "extracted"

    # F. Progress to chunked
    prog_res2 = client.post(
        f"/content/jobs/{job_id}/progress",
        json={"target_stage": "chunked", "metrics": {"chunks_count": 60}},
        headers=lecturer_headers,
    )
    assert prog_res2.status_code == 200
    assert prog_res2.json()["data"]["status"] == "chunked"

    # G. Progress to indexed
    prog_res3 = client.post(
        f"/content/jobs/{job_id}/progress",
        json={"target_stage": "indexed", "metrics": {"indexed_count": 60}},
        headers=lecturer_headers,
    )
    assert prog_res3.status_code == 200
    assert prog_res3.json()["data"]["status"] == "indexed"

    # H. Complete job -> ready
    complete_res = client.post(
        f"/content/jobs/{job_id}/complete",
        json={"metrics": {"total_time_ms": 2500}},
        headers=lecturer_headers,
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["data"]["status"] == "ready"

    # I. Check asset status -> ready
    asset_check = client.get(
        f"/content/assets/{asset_id}",
        headers=lecturer_headers,
    )
    assert asset_check.status_code == 200
    assert asset_check.json()["data"]["ingestion_status"] == "ready"

    # J. Trigger reprocess -> creates Run #2 in queued status
    reprocess_res = client.post(
        f"/content/assets/{asset_id}/reprocess",
        json={"correlation_id": "reprocess-corr-2"},
        headers=lecturer_headers,
    )
    assert reprocess_res.status_code == 201, reprocess_res.text
    run2_data = reprocess_res.json()["data"]
    run2_id = run2_data["id"]
    assert run2_data["run_number"] == 2
    assert run2_data["status"] == "queued"
    assert run2_id != job_id

    # K. Start run 2 then fail it
    client.post(
        f"/content/jobs/{run2_id}/start?stage=ocr",
        headers=lecturer_headers,
    )
    fail_res = client.post(
        f"/content/jobs/{run2_id}/fail",
        json={
            "error_code": "OCR_FAILED",
            "error_message": "Document unreadable",
            "is_retryable": True,
        },
        headers=lecturer_headers,
    )
    assert fail_res.status_code == 200
    assert fail_res.json()["data"]["status"] == "failed"

    # L. Retry run 2
    retry_res = client.post(
        f"/content/jobs/{run2_id}/retry",
        json={"delay_seconds": 20},
        headers=lecturer_headers,
    )
    assert retry_res.status_code == 200
    assert retry_res.json()["data"]["status"] == "queued"
    assert retry_res.json()["data"]["attempt_count"] == 2

    # M. List jobs for asset -> returns 2 runs
    list_res = client.get(
        f"/content/assets/{asset_id}/jobs",
        headers=lecturer_headers,
    )
    assert list_res.status_code == 200
    assert list_res.json()["meta"]["total"] == 2

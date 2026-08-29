from uuid import uuid4

import pytest
from app.application.curriculum.curriculum_source_service import (
    CurriculumSourceService,
)
from app.bootstrap.container import build_container
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


@pytest.mark.asyncio
async def test_curriculum_source_api_lifecycle_and_rbac(client) -> None:
    # 1. Admin setup
    admin_id, admin_token = await register_and_authenticate(
        client, f"curriculum-admin-{uuid4()}@example.com"
    )
    admin_tenant_id, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    # 2. Lecturer setup
    lecturer_id, lecturer_token = await register_and_authenticate(
        client, f"curriculum-lecturer-{uuid4()}@example.com"
    )
    _, lecturer_slug, _, _ = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer_headers = headers(lecturer_token, lecturer_slug)

    # 3. Student setup
    student_id, student_token = await register_and_authenticate(
        client, f"curriculum-student-{uuid4()}@example.com"
    )
    _, student_slug, _, _ = await seed_tenant_context(student_id, "student")
    student_headers = headers(student_token, student_slug)

    # 4. Student attempt to create source -> 403 Forbidden
    student_create = client.post(
        "/curriculum/sources",
        headers=student_headers,
        json={
            "code": "NUC_STUDENT_FAIL",
            "name": "Should Fail",
            "base_url": "https://fail.example.com",
        },
    )
    assert student_create.status_code == 403

    # 5. Student attempt to read sources -> 403 Forbidden (internal ops endpoint)
    student_read = client.get("/curriculum/sources", headers=student_headers)
    assert student_read.status_code == 403

    # 6. Admin creates source -> 201 Created
    unique_code = f"NUC_CCMAS_{uuid4().hex[:6].upper()}"
    create_res = client.post(
        "/curriculum/sources",
        headers=admin_headers,
        json={
            "code": unique_code,
            "name": "National Universities Commission Standard",
            "base_url": "https://ccmas.nuc.edu.ng",
            "source_type": "official_benchmark",
            "sync_frequency_days": 30,
            "parser_version": "v1.0",
        },
    )
    assert create_res.status_code == 201, create_res.text
    source_data = create_res.json()["data"]
    source_id = source_data["id"]
    assert source_data["code"] == unique_code
    assert source_data["status"] == "active"

    # 7. Duplicate code creation -> 409 Conflict
    dup_res = client.post(
        "/curriculum/sources",
        headers=admin_headers,
        json={
            "code": unique_code,
            "name": "Duplicate Code",
            "base_url": "https://ccmas.nuc.edu.ng",
        },
    )
    assert dup_res.status_code == 409

    # 8. Lecturer reads source details -> 200 OK
    get_res = client.get(f"/curriculum/sources/{source_id}", headers=lecturer_headers)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == source_id

    # 9. Lecturer lists sources -> 200 OK
    list_res = client.get("/curriculum/sources", headers=lecturer_headers)
    assert list_res.status_code == 200
    sources = list_res.json()["data"]
    assert any(s["id"] == source_id for s in sources)

    # 10. Admin triggers sync -> 202 Accepted
    sync_res = client.post(
        f"/curriculum/sources/{source_id}/sync", headers=admin_headers
    )
    assert sync_res.status_code == 202
    sync_data = sync_res.json()["data"]
    assert "job_id" in sync_data
    assert sync_data["status"] == "queued"

    # 11. Seed a snapshot via service and verify listing API
    service = build_container().get(CurriculumSourceService)
    sha_test = "e" * 64
    await service.record_snapshot(
        source_id=source_id,
        source_url="https://ccmas.nuc.edu.ng/csc.pdf",
        content_sha256=sha_test,
        raw_artifact_uri="s3://build-artifacts/ccmas/csc.pdf",
    )

    snap_list_res = client.get(
        f"/curriculum/sources/{source_id}/snapshots", headers=lecturer_headers
    )
    assert snap_list_res.status_code == 200
    snapshots_data = snap_list_res.json()
    assert snapshots_data["meta"]["total"] == 1
    assert snapshots_data["data"][0]["content_sha256"] == sha_test
    # Verify raw storage URI is NOT leaked in API response
    assert "raw_artifact_uri" not in snapshots_data["data"][0]

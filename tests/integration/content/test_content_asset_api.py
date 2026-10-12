from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)
from tests.integration.content.test_content_source_api import add_membership


@pytest.mark.asyncio
async def test_content_asset_api_lifecycle_and_deduplication(client) -> None:
    # 1. Admin setup (Tenant A)
    admin_id, admin_token = await register_and_authenticate(client, f"asset-admin-{uuid4()}@example.com")
    tenant_a_id, tenant_a_slug, _, _ = await seed_tenant_context(admin_id, "admin")

    # 2. Lecturer setup (Tenant A)
    lecturer_a_id, lecturer_a_token = await register_and_authenticate(client, f"asset-lecturer-a-{uuid4()}@example.com")
    await add_membership(lecturer_a_id, tenant_a_id, "lecturer")
    lecturer_a_headers = headers(lecturer_a_token, tenant_a_slug)

    # 3. Student setup (Tenant A)
    student_id, student_token = await register_and_authenticate(client, f"asset-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_a_id, "student")
    student_headers = headers(student_token, tenant_a_slug)

    # 4. Lecturer in Tenant B
    lecturer_b_id, lecturer_b_token = await register_and_authenticate(client, f"asset-lecturer-b-{uuid4()}@example.com")
    tenant_b_id, tenant_b_slug, _, _ = await seed_tenant_context(lecturer_b_id, "lecturer")
    lecturer_b_headers = headers(lecturer_b_token, tenant_b_slug)

    # 5. Create ContentSource in Tenant A
    src_code_a = f"CSC301_SRC_{uuid4().hex[:6].upper()}"
    src_res_a = client.post(
        "/content/sources",
        headers=lecturer_a_headers,
        json={
            "code": src_code_a,
            "name": "CSC301 Data Structures & Algorithms",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert src_res_a.status_code == 201, src_res_a.text
    source_a_id = src_res_a.json()["data"]["id"]

    # 6. Student upload attempt -> 403 Forbidden
    sha_payload = "7" * 64
    student_upload = client.post(
        f"/content/sources/{source_a_id}/assets",
        headers=student_headers,
        json={
            "file_name": "illegal_student_upload.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 1024,
            "content_sha256": sha_payload,
            "storage_uri": "s3://bucket/test.pdf",
        },
    )
    assert student_upload.status_code == 403

    # 7. Lecturer A uploads asset #1 -> 201 Created (is_deduplicated: false)
    upload_1 = client.post(
        f"/content/sources/{source_a_id}/assets",
        headers=lecturer_a_headers,
        json={
            "file_name": "CSC301_Lecture_01.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 204800,
            "content_sha256": sha_payload,
            "storage_uri": "s3://build-content/tenants/tenant_a/csc301_l1.pdf",
            "metadata": {"lecture": 1, "semester": 1},
        },
    )
    assert upload_1.status_code == 201, upload_1.text
    asset_1_data = upload_1.json()["data"]
    asset_1_id = asset_1_data["id"]
    assert asset_1_data["content_sha256"] == sha_payload
    assert asset_1_data["is_deduplicated"] is False
    assert asset_1_data["asset_version"] == 1
    assert asset_1_data["status"] == "active"
    assert asset_1_data["ingestion_status"] == "uploaded"

    # 8. Lecturer A uploads identical bytes (renamed file) -> 200 OK (is_deduplicated: true, returns asset #1)
    upload_dup = client.post(
        f"/content/sources/{source_a_id}/assets",
        headers=lecturer_a_headers,
        json={
            "file_name": "CSC301_Lecture_01_FINAL.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 204800,
            "content_sha256": sha_payload,
            "storage_uri": "s3://build-content/tenants/tenant_a/csc301_l1_final.pdf",
        },
    )
    assert upload_dup.status_code == 200, upload_dup.text
    dup_data = upload_dup.json()["data"]
    assert dup_data["id"] == asset_1_id
    assert dup_data["is_deduplicated"] is True

    # 9. Tenant B creates their own source and uploads the same SHA-256
    # -> 201 Created (isolated tenant deduplication domain)
    src_code_b = f"CSC301_UNILAG_{uuid4().hex[:6].upper()}"
    src_res_b = client.post(
        "/content/sources",
        headers=lecturer_b_headers,
        json={
            "code": src_code_b,
            "name": "UNILAG CSC301 Courseware",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert src_res_b.status_code == 201, src_res_b.text
    source_b_id = src_res_b.json()["data"]["id"]

    upload_tenant_b = client.post(
        f"/content/sources/{source_b_id}/assets",
        headers=lecturer_b_headers,
        json={
            "file_name": "UNILAG_CSC301.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 204800,
            "content_sha256": sha_payload,
            "storage_uri": "s3://build-content/tenants/tenant_b/unilag_csc301.pdf",
        },
    )
    assert upload_tenant_b.status_code == 201, upload_tenant_b.text
    asset_b_data = upload_tenant_b.json()["data"]
    assert asset_b_data["id"] != asset_1_id
    assert asset_b_data["tenant_id"] == tenant_b_id
    assert asset_b_data["is_deduplicated"] is False

    # 10. Student reads asset #1 details -> 200 OK
    get_res = client.get(f"/content/assets/{asset_1_id}", headers=student_headers)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == asset_1_id

    # 11. Foreign lecturer attempts GET on Tenant A asset -> 404 Not Found (tenant-isolated)
    foreign_get = client.get(f"/content/assets/{asset_1_id}", headers=lecturer_b_headers)
    assert foreign_get.status_code == 404

    # 12. Versioning: Lecturer A uploads v2 of the document
    sha_v2 = "8" * 64
    ver_res = client.post(
        f"/content/assets/{asset_1_id}/version",
        headers=lecturer_a_headers,
        json={
            "file_name": "CSC301_Lecture_01_2026_Edition.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 300000,
            "content_sha256": sha_v2,
            "storage_uri": "s3://build-content/tenants/tenant_a/csc301_v2.pdf",
            "metadata": {"edition": 2026},
        },
    )
    assert ver_res.status_code == 201, ver_res.text
    v2_data = ver_res.json()["data"]
    v2_id = v2_data["id"]
    assert v2_data["asset_version"] == 2
    assert v2_data["parent_asset_id"] == asset_1_id
    assert v2_data["status"] == "active"

    # Parent asset is now superseded
    parent_check = client.get(f"/content/assets/{asset_1_id}", headers=lecturer_a_headers)
    assert parent_check.status_code == 200
    assert parent_check.json()["data"]["status"] == "superseded"

    # 13. List assets for source A -> returns both v1 and v2
    list_res = client.get(f"/content/sources/{source_a_id}/assets", headers=student_headers)
    assert list_res.status_code == 200
    listed_assets = list_res.json()["data"]
    assert len(listed_assets) == 2
    listed_ids = [a["id"] for a in listed_assets]
    assert v2_id in listed_ids
    assert asset_1_id in listed_ids

    # 14. Revoke asset v2
    rev_res = client.post(
        f"/content/assets/{v2_id}/revoke",
        headers=lecturer_a_headers,
        json={"reason": "Contains inaccurate algorithm complexity proofs"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["data"]["status"] == "revoked"

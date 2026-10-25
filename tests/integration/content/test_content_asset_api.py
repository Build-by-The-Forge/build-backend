from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.uploads import pdf_bytes, upload_asset


def upload_version(client, asset_id, *, headers, data, key=None, name="v2.pdf"):
    request_headers = dict(headers) | {"Idempotency-Key": key or f"k-{uuid4().hex}", "Content-Type": "application/octet-stream"}
    return client.post(
        f"/content/assets/{asset_id}/versions/upload", params={"file_name": name}, headers=request_headers, content=data
    )


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

    lecture_1 = pdf_bytes()

    # 6. Student upload attempt -> 403 Forbidden
    student_upload = upload_asset(client, source_a_id, headers=student_headers, data=lecture_1, name="illegal.pdf")
    assert student_upload.status_code == 403

    # 7. Lecturer A uploads asset #1 -> 201 Created
    upload_1 = upload_asset(client, source_a_id, headers=lecturer_a_headers, data=lecture_1, name="CSC301_Lecture_01.pdf")
    assert upload_1.status_code == 201, upload_1.text
    asset_1_data = upload_1.json()["data"]
    asset_1_id = asset_1_data["id"]
    assert asset_1_data["file_size_bytes"] == len(lecture_1)
    assert asset_1_data["asset_version"] == 1
    assert asset_1_data["status"] == "active"
    assert asset_1_data["ingestion_status"] == "uploaded"

    # 8. Identical bytes under another name and key -> 409 DUPLICATE_CONTENT,
    # naming asset #1 (one asset per tenant and SHA-256, migration 0016)
    upload_dup = upload_asset(client, source_a_id, headers=lecturer_a_headers, data=lecture_1, name="FINAL.pdf")
    assert upload_dup.status_code == 409, upload_dup.text
    assert upload_dup.json()["error"]["code"] == "DUPLICATE_CONTENT"
    assert upload_dup.json()["error"]["existing_asset_id"] == asset_1_id

    # 9. Tenant B uploads the same bytes -> 201 Created (isolated tenant
    # deduplication domain)
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

    upload_tenant_b = upload_asset(client, source_b_id, headers=lecturer_b_headers, data=lecture_1, name="UNILAG.pdf")
    assert upload_tenant_b.status_code == 201, upload_tenant_b.text
    asset_b_data = upload_tenant_b.json()["data"]
    assert asset_b_data["id"] != asset_1_id
    assert asset_b_data["tenant_id"] == tenant_b_id

    # 10. Student reads asset #1 details -> 200 OK
    get_res = client.get(f"/content/assets/{asset_1_id}", headers=student_headers)
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == asset_1_id

    # 11. Foreign lecturer attempts GET on Tenant A asset -> 404 Not Found (tenant-isolated)
    foreign_get = client.get(f"/content/assets/{asset_1_id}", headers=lecturer_b_headers)
    assert foreign_get.status_code == 404

    # 12. Versioning: Lecturer A uploads v2 of the document
    ver_res = upload_version(client, asset_1_id, headers=lecturer_a_headers, data=pdf_bytes(), name="2026_Edition.pdf")
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
    listed_ids = [a["id"] for a in list_res.json()["data"]]
    assert sorted(listed_ids) == sorted([v2_id, asset_1_id])

    # 14. Revoke asset v2
    rev_res = client.post(
        f"/content/assets/{v2_id}/revoke",
        headers=lecturer_a_headers,
        json={"reason": "Contains inaccurate algorithm complexity proofs"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["data"]["status"] == "revoked"


@pytest.mark.asyncio
async def test_the_retired_routes_answer_410_and_create_nothing(client) -> None:
    """P3-1 PR 3b: registration with a client-supplied storage_uri, and the
    old version route, are retired. Any payload, valid or not, is refused
    without being read; nothing is created or superseded."""
    admin_id, _ = await register_and_authenticate(client, f"retired-admin-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    lecturer_id, token = await register_and_authenticate(client, f"retired-lecturer-{uuid4()}@example.com")
    await add_membership(lecturer_id, tenant_id, "lecturer")
    h = headers(token, slug)
    source_id = client.post(
        "/content/sources",
        headers=h,
        json={
            "code": f"RET_{uuid4().hex[:8].upper()}",
            "name": "Retired route notes",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    ).json()["data"]["id"]
    asset_id = upload_asset(client, source_id, headers=h).json()["data"]["id"]
    legacy_payload = {
        "file_name": "a.pdf",
        "mime_type": "application/pdf",
        "file_size_bytes": 10,
        "content_sha256": "a" * 64,
        "storage_uri": "s3://anywhere/a.pdf",
    }

    register = client.post(f"/content/sources/{source_id}/assets", headers=h, json=legacy_payload)
    register_garbage = client.post(f"/content/sources/{source_id}/assets", headers=h, content=b"not json")
    version = client.post(f"/content/assets/{asset_id}/version", headers=h, json=legacy_payload)

    assert register.status_code == register_garbage.status_code == 410
    assert register.json()["error"]["code"] == "ASSET_REGISTRATION_RETIRED"
    assert "/assets/upload" in register.json()["error"]["message"]
    assert version.status_code == 410
    assert version.json()["error"]["code"] == "ASSET_VERSION_RETIRED"
    assert "/versions/upload" in version.json()["error"]["message"]
    listed = client.get(f"/content/sources/{source_id}/assets", headers=h).json()["data"]
    assert [(a["id"], a["status"]) for a in listed] == [(asset_id, "active")]

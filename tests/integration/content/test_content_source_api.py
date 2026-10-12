from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


async def add_membership(user_id: str, tenant_id: str, role: str) -> None:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add(
            MembershipModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_content_source_api_lifecycle_and_rbac(client) -> None:
    # 1. Admin setup (Tenant A)
    admin_id, admin_token = await register_and_authenticate(client, f"content-admin-{uuid4()}@example.com")
    admin_tenant_id, admin_slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin_headers = headers(admin_token, admin_slug)

    # 2. Lecturer setup (Tenant A)
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"content-lecturer-{uuid4()}@example.com")
    await add_membership(lecturer_id, admin_tenant_id, "lecturer")
    lecturer_headers = headers(lecturer_token, admin_slug)

    # 3. Student setup (Tenant A)
    student_id, student_token = await register_and_authenticate(client, f"content-student-{uuid4()}@example.com")
    await add_membership(student_id, admin_tenant_id, "student")
    student_headers = headers(student_token, admin_slug)

    # 4. Foreign Tenant Lecturer (Tenant B)
    foreign_id, foreign_token = await register_and_authenticate(client, f"foreign-lecturer-{uuid4()}@example.com")
    foreign_tenant_id, foreign_slug, _, _ = await seed_tenant_context(foreign_id, "lecturer")
    foreign_headers = headers(foreign_token, foreign_slug)

    # 5. Student attempt to create content source -> 403 Forbidden
    student_create = client.post(
        "/content/sources",
        headers=student_headers,
        json={
            "code": "STUDENT_SRC_FAIL",
            "name": "Student Should Fail",
            "source_type": "lecturer_upload",
            "authority_level": "user_provided",
            "visibility": "tenant",
        },
    )
    assert student_create.status_code == 403

    # 6. Admin creates platform-wide regulatory source -> 201 Created
    reg_code = f"CCMAS_CS_{uuid4().hex[:6].upper()}"
    reg_create = client.post(
        "/content/sources",
        headers=admin_headers,
        json={
            "code": reg_code,
            "name": "NUC CCMAS Computer Science",
            "source_type": "ccmas",
            "authority_level": "regulatory",
            "visibility": "platform",
            "source_url": "https://ccmas.nuc.edu.ng",
            "description": "National benchmark curriculum",
        },
    )
    assert reg_create.status_code == 201, reg_create.text
    reg_data = reg_create.json()["data"]
    reg_source_id = reg_data["id"]
    assert reg_data["code"] == reg_code
    assert reg_data["authority_level"] == "regulatory"
    assert reg_data["visibility"] == "platform"
    assert reg_data["status"] == "active"

    # 7. Lecturer creates tenant-scoped institutional source -> 201 Created
    inst_code = f"CSC201_NOTES_{uuid4().hex[:6].upper()}"
    inst_create = client.post(
        "/content/sources",
        headers=lecturer_headers,
        json={
            "code": inst_code,
            "name": "CSC201 Lecture Slides & Notes",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
            "author_name": "Dr. Adewale",
            "description": "Weekly slide decks and lab handouts",
        },
    )
    assert inst_create.status_code == 201, inst_create.text
    inst_data = inst_create.json()["data"]
    inst_source_id = inst_data["id"]
    assert inst_data["tenant_id"] == admin_tenant_id
    assert inst_data["authority_level"] == "institutional"

    # 8. Duplicate code in same tenant -> 409 Conflict
    dup_create = client.post(
        "/content/sources",
        headers=lecturer_headers,
        json={
            "code": inst_code,
            "name": "Duplicate Code",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert dup_create.status_code == 409

    # 9. Student reads sources list -> 200 OK (sees Platform + Tenant A)
    student_list = client.get("/content/sources", headers=student_headers)
    assert student_list.status_code == 200
    student_sources = student_list.json()["data"]
    student_codes = [s["code"] for s in student_sources]
    assert reg_code in student_codes
    assert inst_code in student_codes

    # 10. Foreign Tenant Lecturer lists sources -> does NOT see Tenant A's private source
    foreign_list = client.get("/content/sources", headers=foreign_headers)
    assert foreign_list.status_code == 200
    foreign_sources = foreign_list.json()["data"]
    foreign_codes = [s["code"] for s in foreign_sources]
    assert reg_code in foreign_codes  # Platform source is visible
    assert inst_code not in foreign_codes  # Tenant A private source is HIDDEN

    # 11. Foreign Lecturer attempts direct GET on Tenant A source -> 403 Forbidden
    foreign_get = client.get(f"/content/sources/{inst_source_id}", headers=foreign_headers)
    assert foreign_get.status_code == 403

    # 12. Lecturer updates metadata -> 200 OK
    update_res = client.patch(
        f"/content/sources/{inst_source_id}",
        headers=lecturer_headers,
        json={
            "name": "CSC201 Object Oriented Programming Notes (Updated)",
            "publisher": "FUTA Press",
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["data"]["name"] == "CSC201 Object Oriented Programming Notes (Updated)"
    assert update_res.json()["data"]["publisher"] == "FUTA Press"

    # 13. Deprecate source -> 200 OK
    dep_res = client.post(
        f"/content/sources/{inst_source_id}/deprecate",
        headers=lecturer_headers,
        json={"reason": "Replaced by semester 2 revisions"},
    )
    assert dep_res.status_code == 200
    assert dep_res.json()["data"]["status"] == "deprecated"

    # 14. Reactivate source -> 200 OK
    act_res = client.post(
        f"/content/sources/{inst_source_id}/activate",
        headers=lecturer_headers,
    )
    assert act_res.status_code == 200
    assert act_res.json()["data"]["status"] == "active"

    # 15. Revoke source -> 200 OK
    rev_res = client.post(
        f"/content/sources/{inst_source_id}/revoke",
        headers=lecturer_headers,
        json={"reason": "Withdrawn by department head"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["data"]["status"] == "revoked"

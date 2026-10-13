from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    MembershipModel,
    TenantModel,
)
from tests.integration.identity_helpers import verify_email


async def seed_write_context(user_id: str, role: str) -> tuple[str, str, str]:
    tenant_id = str(uuid4())
    tenant_slug = f"write-{uuid4()}"
    faculty_id = str(uuid4())
    department_id = str(uuid4())
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Write Tenant",
                slug=tenant_slug,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            FacultyModel(
                id=faculty_id,
                tenant_id=tenant_id,
                name="Write Faculty",
                slug=f"faculty-{uuid4()}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            DepartmentModel(
                id=department_id,
                tenant_id=tenant_id,
                faculty_id=faculty_id,
                name="Write Department",
                slug=f"department-{uuid4()}",
                code=f"D{uuid4().hex[:8].upper()}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
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

    return tenant_id, tenant_slug, department_id


async def register_and_authenticate(client, email: str) -> tuple[str, str]:
    payload = {"email": email, "password": "StrongPass123!"}
    registered = client.post("/identity/users", json=payload)
    assert registered.status_code == 201
    verify_email(client, payload["email"])
    user_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=payload)
    assert authenticated.status_code == 200
    return user_id, authenticated.json()["data"]["access_token"]


def course_payload(department_id: str, code: str = "WRT101") -> dict[str, object]:
    return {
        "department_id": department_id,
        "code": code,
        "title": "Secure Catalogue Writes",
        "slug": f"secure-{code.lower()}",
        "credit_units": 3,
        "level": 200,
        "semester": 1,
        "description": "Created through an authorized tenant context",
    }


@pytest.mark.asyncio
async def test_course_creation_requires_authentication(client):
    response = client.post("/catalogue/courses/", json={})

    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_course_creation_requires_tenant_context(client):
    _, access_token = await register_and_authenticate(client, f"write-no-tenant-{uuid4()}@example.com")

    response = client.post(
        "/catalogue/courses/",
        headers={"Authorization": f"Bearer {access_token}"},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_create_course(client):
    user_id, access_token = await register_and_authenticate(client, f"write-student-{uuid4()}@example.com")
    _, tenant_slug, department_id = await seed_write_context(user_id, "student")

    response = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json=course_payload(department_id, "STU101"),
    )

    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_non_member_cannot_create_course(client):
    _, access_token = await register_and_authenticate(client, f"write-non-member-{uuid4()}@example.com")
    _, tenant_slug, department_id = await seed_write_context(str(uuid4()), "lecturer")

    response = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json=course_payload(department_id, "NMB101"),
    )

    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_lecturer_course_is_owned_by_context_tenant(client):
    user_id, access_token = await register_and_authenticate(client, f"write-lecturer-{uuid4()}@example.com")
    tenant_id, tenant_slug, department_id = await seed_write_context(user_id, "lecturer")

    response = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json=course_payload(department_id, "LEC101"),
    )

    assert response.status_code == 201
    course_id = response.json()["data"]["id"]
    async with SessionLocal() as session:
        course = await session.scalar(select(CourseModel).where(CourseModel.id == course_id))

    assert course is not None
    assert course.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_client_tenant_id_is_rejected(client):
    user_id, access_token = await register_and_authenticate(client, f"write-injection-{uuid4()}@example.com")
    tenant_id, tenant_slug, department_id = await seed_write_context(user_id, "lecturer")

    response = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json={**course_payload(department_id, "INJ101"), "tenant_id": str(uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["data"] == {}
    assert tenant_id not in response.text

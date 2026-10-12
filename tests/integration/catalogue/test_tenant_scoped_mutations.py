from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    MembershipModel,
    TenantModel,
)
from sqlalchemy import select
from tests.integration.identity_helpers import verify_email


async def seed_course_context(client, role: str = "lecturer") -> tuple[str, str, str, str, str]:
    payload = {"email": f"mutation-{uuid4()}@example.com", "password": "StrongPass123!"}
    registered = client.post("/identity/users", json=payload)
    assert registered.status_code == 201
    verify_email(client, payload["email"])
    user_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=payload)
    assert authenticated.status_code == 200
    token = authenticated.json()["data"]["access_token"]

    tenant_id = str(uuid4())
    tenant_slug = f"mutation-{uuid4()}"
    department_id = str(uuid4())
    course_id = str(uuid4())
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        faculty_id = str(uuid4())
        session.add_all(
            [
                TenantModel(
                    id=tenant_id,
                    name="Mutation Tenant",
                    slug=tenant_slug,
                    status="active",
                    created_at=now,
                    updated_at=now,
                ),
                FacultyModel(
                    id=faculty_id,
                    tenant_id=tenant_id,
                    name="Mutation Faculty",
                    slug=f"faculty-{uuid4()}",
                    status="active",
                    created_at=now,
                    updated_at=now,
                ),
                DepartmentModel(
                    id=department_id,
                    tenant_id=tenant_id,
                    faculty_id=faculty_id,
                    name="Mutation Department",
                    slug=f"department-{uuid4()}",
                    code=f"D{uuid4().hex[:8].upper()}",
                    status="active",
                    created_at=now,
                    updated_at=now,
                ),
                MembershipModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role=role,
                    status="active",
                    created_at=now,
                    updated_at=now,
                ),
                CourseModel(
                    id=course_id,
                    tenant_id=tenant_id,
                    department_id=department_id,
                    code=f"M{uuid4().hex[:5].upper()}",
                    title="Original Course Title",
                    slug=f"original-{uuid4()}",
                    credit_units=3,
                    level=200,
                    semester=1,
                    status="active",
                    description="Original description",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    return tenant_id, tenant_slug, department_id, course_id, token


def headers(token: str, tenant_slug: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": tenant_slug}


@pytest.mark.asyncio
async def test_course_update_requires_authorization(client):
    response = client.patch("/catalogue/courses/course-id", json={"title": "New"})
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_update_course(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "student")

    response = client.patch(
        f"/catalogue/courses/{course_id}",
        headers=headers(token, tenant_slug),
        json={"title": "Student Update"},
    )

    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_client_tenant_id_is_rejected_on_update(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client)

    response = client.patch(
        f"/catalogue/courses/{course_id}",
        headers=headers(token, tenant_slug),
        json={"title": "Injected Update", "tenant_id": str(uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_lecturer_updates_course_in_own_tenant(client):
    tenant_id, tenant_slug, _, course_id, token = await seed_course_context(client)

    response = client.patch(
        f"/catalogue/courses/{course_id}",
        headers=headers(token, tenant_slug),
        json={"title": "Updated Course Title", "description": "Updated description"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "Updated Course Title"
    async with SessionLocal() as session:
        course = await session.scalar(select(CourseModel).where(CourseModel.id == course_id))
    assert course is not None
    assert course.tenant_id == tenant_id
    assert course.title == "Updated Course Title"


@pytest.mark.asyncio
async def test_cross_tenant_course_update_returns_not_found(client):
    _, tenant_a_slug, _, course_id, token = await seed_course_context(client)
    _, tenant_b_slug, _, _, _ = await seed_course_context(client)

    response = client.patch(
        f"/catalogue/courses/{course_id}",
        headers=headers(token, tenant_b_slug),
        json={"title": "Cross Tenant Update"},
    )

    assert response.status_code == 403
    assert response.json()["success"] is False
    assert tenant_a_slug != tenant_b_slug


@pytest.mark.asyncio
async def test_course_archive_and_publish_are_tenant_scoped(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "faculty_admin")
    request_headers = headers(token, tenant_slug)

    archived = client.post(f"/catalogue/courses/{course_id}/archive", headers=request_headers)
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"

    published = client.post(f"/catalogue/courses/{course_id}/publish", headers=request_headers)
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_student_cannot_archive_or_publish_course(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "student")
    request_headers = headers(token, tenant_slug)

    archive = client.post(f"/catalogue/courses/{course_id}/archive", headers=request_headers)
    publish = client.post(f"/catalogue/courses/{course_id}/publish", headers=request_headers)

    assert archive.status_code == 403
    assert publish.status_code == 403

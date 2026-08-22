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


async def seed_catalogue(tenant_slug: str, user_id: str, code: str) -> tuple[str, str]:
    tenant_id = str(uuid4())
    faculty_id = str(uuid4())
    department_id = str(uuid4())
    course_id = str(uuid4())
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name=tenant_slug.upper(),
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
                name="Faculty",
                slug=f"faculty-{tenant_slug}",
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
                name="Computer Science",
                slug=f"computer-science-{tenant_slug}",
                code=f"D{code}",
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
                role="student",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CourseModel(
                id=course_id,
                tenant_id=tenant_id,
                department_id=department_id,
                code=code,
                title=f"Course {code}",
                slug=f"course-{code.lower()}",
                credit_units=3,
                level=200,
                semester=1,
                status="active",
                description="Tenant-scoped course",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    return tenant_id, course_id


async def register_and_authenticate(client, email: str) -> tuple[str, str]:
    payload = {"email": email, "password": "StrongPass123!"}
    registered = client.post("/identity/users", json=payload)
    assert registered.status_code == 201
    user_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=payload)
    assert authenticated.status_code == 200
    return user_id, authenticated.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_catalogue_reads_require_authentication_and_tenant_context(client):
    response = client.get("/catalogue/courses/")

    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_catalogue_list_is_scoped_to_member_tenant(client):
    user_id, access_token = await register_and_authenticate(
        client, f"catalogue-{uuid4()}@example.com"
    )
    tenant_a_slug = f"tenant-a-{uuid4()}"
    tenant_b_slug = f"tenant-b-{uuid4()}"
    _, course_a_id = await seed_catalogue(tenant_a_slug, user_id, "CAT101")
    _, course_b_id = await seed_catalogue(tenant_b_slug, str(uuid4()), "CAT201")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Tenant-Slug": tenant_a_slug,
    }
    response = client.get("/catalogue/courses/", headers=headers)

    assert response.status_code == 200
    course_ids = {course["id"] for course in response.json()["data"]}
    assert course_a_id in course_ids
    assert course_b_id not in course_ids


@pytest.mark.asyncio
async def test_catalogue_direct_lookup_cannot_cross_tenants(client):
    user_id, access_token = await register_and_authenticate(
        client, f"lookup-{uuid4()}@example.com"
    )
    tenant_a_slug = f"lookup-a-{uuid4()}"
    tenant_b_slug = f"lookup-b-{uuid4()}"
    await seed_catalogue(tenant_a_slug, user_id, "LKP101")
    _, course_b_id = await seed_catalogue(tenant_b_slug, str(uuid4()), "LKP201")

    response = client.get(
        f"/catalogue/courses/{course_b_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_a_slug,
        },
    )

    assert response.status_code == 404
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_catalogue_read_denies_non_member_tenant(client):
    user_id, access_token = await register_and_authenticate(
        client, f"denied-{uuid4()}@example.com"
    )
    tenant_slug = f"denied-{uuid4()}"
    await seed_catalogue(tenant_slug, str(uuid4()), "DEN101")

    response = client.get(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
    )

    assert response.status_code == 403
    assert response.json()["success"] is False

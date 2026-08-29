import uuid
from datetime import datetime, timezone

import pytest
from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    MembershipModel,
    TenantModel,
)


@pytest.mark.asyncio
async def test_create_course_api(client, session):
    # prepare tenant/faculty/department
    tenant_id = str(uuid.uuid4())
    faculty_id = str(uuid.uuid4())
    department_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)

    tenant = TenantModel(
        id=tenant_id,
        name="Test Tenant",
        slug="test-tenant",
        created_at=now,
        updated_at=now,
        status="active",
    )
    faculty = FacultyModel(
        id=faculty_id,
        tenant_id=tenant_id,
        name="Test Faculty",
        slug="test-faculty",
        created_at=now,
        updated_at=now,
        status="active",
    )
    department = DepartmentModel(
        id=department_id,
        tenant_id=tenant_id,
        faculty_id=faculty_id,
        name="Test Department",
        slug="test-department",
        code="DPT",
        created_at=now,
        updated_at=now,
        status="active",
    )

    session.add_all([tenant, faculty, department])
    await session.flush()

    payload = {
        "department_id": department_id,
        "code": "CS201",
        "title": "Algorithms",
        "slug": "algorithms",
        "credit_units": 3,
        "level": 200,
        "semester": 1,
        "description": "Intro to algorithms",
    }

    auth_payload = {
        "email": f"catalogue-{uuid.uuid4()}@example.com",
        "password": "StrongPass123!",
    }
    registered = client.post("/identity/users", json=auth_payload)
    assert registered.status_code == 201
    user_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=auth_payload)
    assert authenticated.status_code == 200
    access_token = authenticated.json()["data"]["access_token"]

    async with SessionLocal() as app_session:
        app_session.add(
            TenantModel(
                id=tenant_id,
                name="Test Tenant",
                slug="test-tenant",
                created_at=now,
                updated_at=now,
                status="active",
            )
        )
        app_session.add(
            FacultyModel(
                id=faculty_id,
                tenant_id=tenant_id,
                name="Test Faculty",
                slug="test-faculty",
                created_at=now,
                updated_at=now,
                status="active",
            )
        )
        app_session.add(
            DepartmentModel(
                id=department_id,
                tenant_id=tenant_id,
                faculty_id=faculty_id,
                name="Test Department",
                slug="test-department",
                code="DPT",
                created_at=now,
                updated_at=now,
                status="active",
            )
        )
        app_session.add(
            MembershipModel(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                role="lecturer",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await app_session.commit()

    resp = client.post(
        "/catalogue/courses/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": "test-tenant",
        },
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    created = data["data"]
    assert created["code"] == payload["code"]

    # list via GET within the authenticated tenant context
    resp2 = client.get(
        "/catalogue/courses/?department_id=%s" % department_id,
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": "test-tenant",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert any(c["code"] == payload["code"] for c in data2["data"])

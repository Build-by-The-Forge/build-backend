from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import ReferenceMaterialModel
from app.infrastructure.db.models.tenant_core import MembershipModel
from sqlalchemy import select
from tests.integration.catalogue.test_tenant_scoped_mutations import (
    headers,
    seed_course_context,
)
from tests.integration.identity_helpers import verify_email


async def create_topic(client, tenant_slug: str, course_id: str, token: str) -> str:
    response = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=headers(token, tenant_slug),
        json={"title": "Materials Topic", "slug": "materials-topic"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def create_reference(client, tenant_slug: str, topic_id: str, token: str) -> dict:
    response = client.post(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=headers(token, tenant_slug),
        json={
            "title": "Course Handbook",
            "material_type": "book",
            "url": "https://example.com/handbook",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.mark.asyncio
async def test_reference_material_creation_requires_authentication(client):
    response = client.post(
        f"/catalogue/topics/{uuid4()}/reference-materials",
        json={"title": "Course Handbook", "material_type": "book"},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_create_reference_material(client):
    tenant_id, tenant_slug, _, course_id, lecturer_token = await seed_course_context(
        client, "lecturer"
    )
    topic_id = await create_topic(client, tenant_slug, course_id, lecturer_token)

    payload = {
        "email": f"student-material-{uuid4()}@example.com",
        "password": "StrongPass123!",
    }
    registered = client.post("/identity/users", json=payload)
    assert registered.status_code == 201
    verify_email(client, payload["email"])
    student_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=payload)
    assert authenticated.status_code == 200
    student_token = authenticated.json()["data"]["access_token"]

    async with SessionLocal() as session:
        session.add(
            MembershipModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                user_id=student_id,
                role="student",
                status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = client.post(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=headers(student_token, tenant_slug),
        json={"title": "Course Handbook", "material_type": "book"},
    )
    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_reference_material_round_trip_and_list(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "lecturer")
    topic_id = await create_topic(client, tenant_slug, course_id, token)
    material = await create_reference(client, tenant_slug, topic_id, token)

    listed = client.get(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=headers(token, tenant_slug),
    )
    assert listed.status_code == 200
    assert listed.json()["data"] == [material]

    async with SessionLocal() as session:
        stored = await session.scalar(
            select(ReferenceMaterialModel).where(
                ReferenceMaterialModel.id == material["id"]
            )
        )
    assert stored is not None
    assert stored.course_id == course_id
    assert stored.title == "Course Handbook"


@pytest.mark.asyncio
async def test_reference_material_update_and_archive(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(
        client, "faculty_admin"
    )
    topic_id = await create_topic(client, tenant_slug, course_id, token)
    material = await create_reference(client, tenant_slug, topic_id, token)
    request_headers = headers(token, tenant_slug)

    updated = client.patch(
        f"/catalogue/reference-materials/{material['id']}",
        headers=request_headers,
        json={"title": "Updated Handbook", "url": "https://example.com/updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "Updated Handbook"

    archived = client.post(
        f"/catalogue/reference-materials/{material['id']}/archive",
        headers=request_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"


@pytest.mark.asyncio
async def test_reference_material_client_tenant_id_is_rejected(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "lecturer")
    topic_id = await create_topic(client, tenant_slug, course_id, token)
    response = client.post(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=headers(token, tenant_slug),
        json={
            "title": "Injected Reference",
            "material_type": "book",
            "tenant_id": str(uuid4()),
        },
    )
    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_reference_material_invalid_payload_returns_validation_error(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "lecturer")
    topic_id = await create_topic(client, tenant_slug, course_id, token)

    response = client.post(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=headers(token, tenant_slug),
        json={"title": "x", "material_type": "unknown"},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_reference_material_cross_tenant_access_is_denied(client):
    _, tenant_a_slug, _, course_a_id, token_a = await seed_course_context(
        client, "lecturer"
    )
    topic_a_id = await create_topic(client, tenant_a_slug, course_a_id, token_a)
    material = await create_reference(client, tenant_a_slug, topic_a_id, token_a)
    _, tenant_b_slug, _, _, token_b = await seed_course_context(client, "faculty_admin")

    response = client.patch(
        f"/catalogue/reference-materials/{material['id']}",
        headers=headers(token_b, tenant_b_slug),
        json={"title": "Cross Tenant Update"},
    )
    assert response.status_code == 404
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_reference_material_missing_parent_and_resource_return_not_found(client):
    _, tenant_slug, _, _, token = await seed_course_context(client, "lecturer")
    request_headers = headers(token, tenant_slug)
    create_response = client.post(
        f"/catalogue/topics/{uuid4()}/reference-materials",
        headers=request_headers,
        json={"title": "Course Handbook", "material_type": "book"},
    )
    update_response = client.patch(
        f"/catalogue/reference-materials/{uuid4()}",
        headers=request_headers,
        json={"title": "Missing"},
    )
    assert create_response.status_code == 404
    assert update_response.status_code == 404

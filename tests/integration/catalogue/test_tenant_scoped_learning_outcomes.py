from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import LearningOutcomeModel
from tests.integration.catalogue.test_tenant_scoped_mutations import (
    headers,
    seed_course_context,
)


async def create_topic(client, tenant_slug: str, course_id: str, token: str) -> str:
    response = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=headers(token, tenant_slug),
        json={"title": "Regression Topic", "slug": "regression-topic"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def create_outcome(
    client,
    tenant_slug: str,
    topic_id: str,
    token: str,
    description: str = "Explain the regression model.",
) -> dict:
    response = client.post(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=headers(token, tenant_slug),
        json={"sequence": 1, "description": description},
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.mark.asyncio
async def test_learning_outcome_creation_requires_authentication(client):
    response = client.post(
        f"/catalogue/topics/{uuid4()}/learning-outcomes",
        json={"description": "Explain the regression model."},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_create_learning_outcome(client):
    user_id, tenant_slug, _, course_id, token = await seed_course_context(client, "student")
    topic_response = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=headers(token, tenant_slug),
        json={"title": "Student Topic", "slug": "student-topic"},
    )
    assert topic_response.status_code == 403
    assert user_id


@pytest.mark.asyncio
async def test_authorized_learning_outcome_round_trip_and_list(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "lecturer")
    topic_id = await create_topic(client, tenant_slug, course_id, token)
    outcome = await create_outcome(client, tenant_slug, topic_id, token)

    listed = client.get(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=headers(token, tenant_slug),
    )
    assert listed.status_code == 200
    assert listed.json()["data"] == [outcome]

    async with SessionLocal() as session:
        stored = await session.scalar(select(LearningOutcomeModel).where(LearningOutcomeModel.id == outcome["id"]))
    assert stored is not None
    assert stored.topic_id == topic_id
    assert stored.description == "Explain the regression model."


@pytest.mark.asyncio
async def test_learning_outcome_update_and_archive(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "faculty_admin")
    topic_id = await create_topic(client, tenant_slug, course_id, token)
    outcome = await create_outcome(client, tenant_slug, topic_id, token)
    request_headers = headers(token, tenant_slug)

    updated = client.patch(
        f"/catalogue/learning-outcomes/{outcome['id']}",
        headers=request_headers,
        json={"description": "Explain how regression models are evaluated."},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["description"] == "Explain how regression models are evaluated."

    archived = client.post(
        f"/catalogue/learning-outcomes/{outcome['id']}/archive",
        headers=request_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"


@pytest.mark.asyncio
async def test_learning_outcome_client_tenant_id_is_rejected(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "lecturer")
    topic_id = await create_topic(client, tenant_slug, course_id, token)

    response = client.post(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=headers(token, tenant_slug),
        json={
            "sequence": 1,
            "description": "Explain the regression model.",
            "tenant_id": str(uuid4()),
        },
    )
    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_learning_outcome_cross_tenant_access_is_denied(client):
    _, tenant_a_slug, _, course_a_id, token_a = await seed_course_context(client, "lecturer")
    topic_a_id = await create_topic(client, tenant_a_slug, course_a_id, token_a)
    outcome = await create_outcome(client, tenant_a_slug, topic_a_id, token_a)
    _, tenant_b_slug, _, _, token_b = await seed_course_context(client, "lecturer")

    response = client.patch(
        f"/catalogue/learning-outcomes/{outcome['id']}",
        headers=headers(token_b, tenant_b_slug),
        json={"description": "Cross tenant mutation attempt."},
    )
    assert response.status_code == 404
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_learning_outcome_missing_parent_and_resource_return_not_found(client):
    _, tenant_slug, _, _, token = await seed_course_context(client, "lecturer")
    request_headers = headers(token, tenant_slug)

    create_response = client.post(
        f"/catalogue/topics/{uuid4()}/learning-outcomes",
        headers=request_headers,
        json={"description": "Explain the regression model."},
    )
    list_response = client.get(
        f"/catalogue/topics/{uuid4()}/learning-outcomes",
        headers=request_headers,
    )
    update_response = client.patch(
        f"/catalogue/learning-outcomes/{uuid4()}",
        headers=request_headers,
        json={"description": "Explain the regression model."},
    )

    assert create_response.status_code == 404
    assert list_response.status_code == 404
    assert update_response.status_code == 404

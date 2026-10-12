from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import CourseModel
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


def headers(token: str, tenant_slug: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Slug": tenant_slug,
    }


async def course_id_for_tenant(tenant_id: str) -> str:
    async with SessionLocal() as session:
        result = await session.scalars(select(CourseModel.id).where(CourseModel.tenant_id == tenant_id))
        course_id = result.first()
    assert course_id is not None
    return course_id


@pytest.mark.asyncio
async def test_assessment_definition_lifecycle_over_http(client):
    user_id, token = await register_and_authenticate(client, f"assessment-api-{uuid4()}@example.com")
    tenant_id, tenant_slug, topic_id, learning_outcome_id = await seed_tenant_context(user_id, "lecturer")
    course_id = await course_id_for_tenant(tenant_id)
    request_headers = headers(token, tenant_slug)

    created = client.post(
        "/assessment/assessments",
        headers=request_headers,
        json={
            "course_id": course_id,
            "title": "Midterm Assessment",
            "instructions": "Answer all questions.",
            "duration_minutes": 60,
            "passing_score": 50,
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["success"] is True
    assessment_id = payload["data"]["id"]
    assert payload["data"]["status"] == "draft"

    question = client.post(
        "/assessment/questions",
        headers=request_headers,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": learning_outcome_id,
            "question_type": "mcq",
            "prompt": "Which structure is FIFO?",
            "options": [
                {"text": "Stack", "display_order": 1, "is_correct": False},
                {"text": "Queue", "display_order": 2, "is_correct": True},
            ],
        },
    )
    assert question.status_code == 201, question.text
    question_id = question.json()["data"]["id"]

    added = client.post(
        f"/assessment/assessments/{assessment_id}/questions",
        headers=request_headers,
        json={"question_id": question_id},
    )
    assert added.status_code == 200, added.text
    assert added.json()["data"]["question_count"] == 1

    listed = client.get(f"/assessment/assessments?course_id={course_id}", headers=request_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [assessment_id]

    retrieved = client.get(f"/assessment/assessments/{assessment_id}", headers=request_headers)
    assert retrieved.status_code == 200
    assert retrieved.json()["data"]["title"] == "Midterm Assessment"

    updated = client.patch(
        f"/assessment/assessments/{assessment_id}",
        headers=request_headers,
        json={"title": "Updated Midterm", "duration_minutes": 90},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "Updated Midterm"

    published = client.post(
        f"/assessment/assessments/{assessment_id}/publish",
        headers=request_headers,
    )
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "published"


@pytest.mark.asyncio
async def test_assessment_api_requires_authentication(client):
    response = client.get("/assessment/assessments")
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_create_assessment(client):
    user_id, token = await register_and_authenticate(client, f"assessment-student-api-{uuid4()}@example.com")
    tenant_id, tenant_slug, _, _ = await seed_tenant_context(user_id, "student")
    course_id = await course_id_for_tenant(tenant_id)

    response = client.post(
        "/assessment/assessments",
        headers=headers(token, tenant_slug),
        json={
            "course_id": course_id,
            "title": "Forbidden Assessment",
            "instructions": "Answer all questions.",
            "duration_minutes": 60,
        },
    )
    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_assessment_api_does_not_cross_tenants(client):
    owner_id, owner_token = await register_and_authenticate(client, f"assessment-owner-{uuid4()}@example.com")
    owner_tenant_id, owner_slug, _, _ = await seed_tenant_context(owner_id, "lecturer")
    course_id = await course_id_for_tenant(owner_tenant_id)
    owner_headers = headers(owner_token, owner_slug)
    created = client.post(
        "/assessment/assessments",
        headers=owner_headers,
        json={
            "course_id": course_id,
            "title": "Private Assessment",
            "instructions": "Answer all questions.",
            "duration_minutes": 60,
        },
    )
    assert created.status_code == 201
    assessment_id = created.json()["data"]["id"]

    other_id, other_token = await register_and_authenticate(client, f"assessment-other-{uuid4()}@example.com")
    _, other_slug, _, _ = await seed_tenant_context(other_id, "lecturer")
    response = client.get(
        f"/assessment/assessments/{assessment_id}",
        headers=headers(other_token, other_slug),
    )
    assert response.status_code == 404

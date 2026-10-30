from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


def headers(token: str, tenant_slug: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Slug": tenant_slug,
    }


async def add_membership(user_id: str, tenant_id: str, role: str) -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(MembershipModel).where(
                MembershipModel.user_id == user_id,
                MembershipModel.tenant_id == tenant_id,
            )
        )
        if existing is None:
            now = datetime.now(timezone.utc)
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
async def test_attempt_api_start_resume_get_list_and_submit(client) -> None:
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"attempt-lecturer-{uuid4()}@example.com")
    tenant_id, tenant_slug, topic_id, learning_outcome_id = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer_headers = headers(lecturer_token, tenant_slug)

    from tests.integration.assessment.test_assessment_api import course_id_for_tenant

    course_id = await course_id_for_tenant(tenant_id)
    assessment = client.post(
        "/assessment/assessments",
        headers=lecturer_headers,
        json={
            "course_id": course_id,
            "title": "Attempt Assessment",
            "instructions": "Answer all questions.",
            "duration_minutes": 30,
        },
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["data"]["id"]

    question = client.post(
        "/assessment/questions",
        headers=lecturer_headers,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": learning_outcome_id,
            "question_type": "mcq",
            "prompt": "Which is FIFO?",
            "options": [
                {"text": "Stack", "display_order": 1, "is_correct": False},
                {"text": "Queue", "display_order": 2, "is_correct": True},
            ],
        },
    )
    assert question.status_code == 201, question.text
    added = client.post(
        f"/assessment/assessments/{assessment_id}/questions",
        headers=lecturer_headers,
        json={"question_id": question.json()["data"]["id"]},
    )
    assert added.status_code == 200, added.text
    published = client.post(
        f"/assessment/assessments/{assessment_id}/publish",
        headers=lecturer_headers,
    )
    assert published.status_code == 200, published.text

    student_id, student_token = await register_and_authenticate(client, f"attempt-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    student_headers = headers(student_token, tenant_slug)

    started = client.post(
        f"/assessment/assessments/{assessment_id}/attempts",
        headers=student_headers,
    )
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["id"]
    assert started.json()["data"]["status"] == "in_progress"

    resumed = client.post(
        f"/assessment/assessments/{assessment_id}/attempts",
        headers=student_headers,
    )
    assert resumed.status_code == 201
    assert resumed.json()["data"]["id"] == attempt_id

    retrieved = client.get(f"/assessment/attempts/{attempt_id}", headers=student_headers)
    assert retrieved.status_code == 200
    assert retrieved.json()["data"]["user_id"] == student_id

    listed = client.get("/assessment/attempts", headers=student_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [attempt_id]

    delivered = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student_headers)
    assert delivered.status_code == 200, delivered.text
    delivered_data = delivered.json()["data"]
    assert delivered_data["assessment_id"] == assessment_id
    assert delivered_data["questions"][0]["sequence"] == 0
    assert delivered_data["questions"][0]["prompt"] == "Which is FIFO?"
    assert delivered_data["questions"][0]["options"] == [
        {"position": 0, "text": "Stack"},
        {"position": 1, "text": "Queue"},
    ]
    assert "is_correct" not in delivered.text
    assert "answer_key" not in delivered.text
    assert "score" not in delivered.text

    submitted = client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student_headers)
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "submitted"

    unavailable = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student_headers)
    assert unavailable.status_code == 404

    # A repeat is safe: test_attempt_deadline.py checks it grades only once.
    duplicate = client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student_headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["status"] == "submitted"


@pytest.mark.asyncio
async def test_attempt_api_requires_authentication(client) -> None:
    response = client.get("/assessment/attempts")
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_start_unpublished_assessment(client) -> None:
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"attempt-draft-lecturer-{uuid4()}@example.com")
    tenant_id, tenant_slug, _, _ = await seed_tenant_context(lecturer_id, "lecturer")
    from tests.integration.assessment.test_assessment_api import course_id_for_tenant

    course_id = await course_id_for_tenant(tenant_id)
    assessment = client.post(
        "/assessment/assessments",
        headers=headers(lecturer_token, tenant_slug),
        json={
            "course_id": course_id,
            "title": "Draft Assessment",
            "instructions": "Not available yet.",
            "duration_minutes": 30,
        },
    )
    assert assessment.status_code == 201
    student_id, student_token = await register_and_authenticate(client, f"attempt-draft-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")

    response = client.post(
        f"/assessment/assessments/{assessment.json()['data']['id']}/attempts",
        headers=headers(student_token, tenant_slug),
    )
    assert response.status_code == 409

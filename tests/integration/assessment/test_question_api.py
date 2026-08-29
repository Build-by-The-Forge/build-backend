from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    LearningOutcomeModel,
    TopicModel,
)
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    MembershipModel,
    TenantModel,
)


async def seed_tenant_context(user_id: str, role: str) -> tuple[str, str, str, str]:
    tenant_id = str(uuid4())
    tenant_slug = f"assessment-{uuid4()}"
    faculty_id = str(uuid4())
    department_id = str(uuid4())
    course_id = str(uuid4())
    topic_id = str(uuid4())
    learning_outcome_id = str(uuid4())
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                name="Assessment Tenant",
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
                name="Assessment Faculty",
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
                name="Assessment Department",
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
        session.add(
            CourseModel(
                id=course_id,
                tenant_id=tenant_id,
                department_id=department_id,
                code=f"Q{uuid4().hex[:5].upper()}",
                title="Assessment Course",
                slug=f"assessment-{uuid4()}",
                credit_units=3,
                level=200,
                semester=1,
                status="active",
                description="Course prepared for assessment API tests",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TopicModel(
                id=topic_id,
                course_id=course_id,
                sequence=1,
                title="Assessment Topic",
                slug=f"assessment-topic-{uuid4()}",
                description="Topic used for assessment API tests",
                level="primary",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            LearningOutcomeModel(
                id=learning_outcome_id,
                topic_id=topic_id,
                sequence=1,
                description="Explain the concept being assessed",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    return tenant_id, tenant_slug, topic_id, learning_outcome_id


async def register_and_authenticate(client, email: str) -> tuple[str, str]:
    payload = {"email": email, "password": "StrongPass123!"}
    registered = client.post("/identity/users", json=payload)
    assert registered.status_code == 201
    user_id = registered.json()["data"]["id"]
    authenticated = client.post("/identity/authenticate", json=payload)
    assert authenticated.status_code == 200
    return user_id, authenticated.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_question_creation_requires_authentication(client):
    response = client.post("/assessment/questions", json={})
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_lecturer_can_create_read_update_publish_and_archive_question(client):
    user_id, access_token = await register_and_authenticate(
        client, f"assessment-lecturer-{uuid4()}@example.com"
    )
    _, tenant_slug, topic_id, learning_outcome_id = await seed_tenant_context(
        user_id, "lecturer"
    )

    payload = {
        "topic_id": topic_id,
        "learning_outcome_id": learning_outcome_id,
        "question_type": "mcq",
        "prompt": "What is supervised learning?",
        "explanation": "It uses labelled training data.",
        "difficulty": "medium",
        "marks": 2,
        "options": [
            {
                "text": "Learning from labelled data",
                "display_order": 1,
                "is_correct": True,
            },
            {"text": "Learning with no data", "display_order": 2, "is_correct": False},
        ],
    }

    response = client.post(
        "/assessment/questions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json=payload,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["success"] is True
    question_id = data["data"]["id"]
    assert data["data"]["prompt"] == payload["prompt"]

    get_response = client.get(
        f"/assessment/questions/{question_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
    )
    assert get_response.status_code == 200
    assert get_response.json()["data"]["id"] == question_id

    patch_response = client.patch(
        f"/assessment/questions/{question_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json={"prompt": "Updated question prompt", "difficulty": "hard"},
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["data"]
    assert updated["prompt"] == "Updated question prompt"
    assert updated["difficulty"] == "hard"

    publish_response = client.post(
        f"/assessment/questions/{question_id}/publish",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["data"]["status"] == "published"

    archive_response = client.post(
        f"/assessment/questions/{question_id}/archive",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["status"] == "archived"


@pytest.mark.asyncio
async def test_student_cannot_create_question(client):
    user_id, access_token = await register_and_authenticate(
        client, f"assessment-student-{uuid4()}@example.com"
    )
    _, tenant_slug, topic_id, _ = await seed_tenant_context(user_id, "student")

    response = client.post(
        "/assessment/questions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
        json={
            "topic_id": topic_id,
            "question_type": "mcq",
            "prompt": "Forbidden prompt",
            "options": [
                {"text": "One", "display_order": 1, "is_correct": True},
                {"text": "Two", "display_order": 2, "is_correct": False},
            ],
        },
    )

    assert response.status_code == 403
    assert response.json()["success"] is False

"""What a student may read of an assessment: nothing unpublished, and no
questions outside an attempt or answer keys at all."""

from uuid import uuid4

import pytest

from tests.integration.assessment.test_assessment_api import course_id_for_tenant
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context


async def assessment_with_question(client, *, published: bool):
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"vis-lecturer-{uuid4()}@example.com")
    tenant_id, slug, topic_id, outcome_id = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer = headers(lecturer_token, slug)
    created = client.post(
        "/assessment/assessments",
        headers=lecturer,
        json={
            "course_id": await course_id_for_tenant(tenant_id),
            "title": "Visibility",
            "instructions": "Answer all questions.",
            "duration_minutes": 30,
        },
    )
    assert created.status_code == 201, created.text
    assessment_id = created.json()["data"]["id"]
    question = client.post(
        "/assessment/questions",
        headers=lecturer,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": outcome_id,
            "question_type": "mcq",
            "prompt": "SECRET-PROMPT",
            "explanation": "SECRET-EXPLANATION",
            "options": [
                {"text": "SECRET-OPTION-A", "display_order": 1, "is_correct": False},
                {"text": "SECRET-OPTION-B", "display_order": 2, "is_correct": True},
            ],
        },
    )
    assert question.status_code == 201, question.text
    question_id = question.json()["data"]["id"]
    added = client.post(
        f"/assessment/assessments/{assessment_id}/questions",
        headers=lecturer,
        json={"question_id": question_id},
    )
    assert added.status_code == 200, added.text
    if published:
        assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=lecturer).status_code == 200
    student_id, student_token = await register_and_authenticate(client, f"vis-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    return lecturer, headers(student_token, slug), assessment_id, question_id


@pytest.mark.asyncio
async def test_a_student_list_excludes_drafts(client):
    lecturer, student, draft_id, _ = await assessment_with_question(client, published=False)
    listed = client.get("/assessment/assessments", headers=student)
    assert listed.status_code == 200
    assert draft_id not in listed.text
    assert "SECRET-PROMPT" not in listed.text
    # M3-E decision 1: staff don't see it on the mobile route either, only on theirs.
    assert draft_id not in client.get("/assessment/assessments", headers=lecturer).text
    assert draft_id in client.get("/assessment/staff/assessments", headers=lecturer).text


@pytest.mark.asyncio
async def test_a_student_list_by_course_excludes_drafts(client):
    lecturer, student, draft_id, _ = await assessment_with_question(client, published=False)
    course_id = client.get(f"/assessment/staff/assessments/{draft_id}", headers=lecturer).json()["data"]["course_id"]
    listed = client.get("/assessment/assessments", headers=student, params={"course_id": course_id})
    assert listed.status_code == 200
    assert draft_id not in listed.text


@pytest.mark.asyncio
async def test_a_draft_by_direct_id_looks_like_it_does_not_exist(client):
    lecturer, student, draft_id, _ = await assessment_with_question(client, published=False)
    draft = client.get(f"/assessment/assessments/{draft_id}", headers=student)
    missing = client.get(f"/assessment/assessments/{uuid4()}", headers=student)
    assert draft.status_code == missing.status_code == 404
    assert draft.json()["error"]["code"] == missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert draft.json()["error"] == missing.json()["error"]
    assert "SECRET" not in draft.text
    assert client.get(f"/assessment/assessments/{draft_id}", headers=lecturer).status_code == 404
    assert client.get(f"/assessment/staff/assessments/{draft_id}", headers=lecturer).json()["data"]["status"] == "draft"


@pytest.mark.asyncio
async def test_a_student_sees_a_published_assessment_without_its_questions(client):
    _, student, assessment_id, _ = await assessment_with_question(client, published=True)
    detail = client.get(f"/assessment/assessments/{assessment_id}", headers=student)
    assert detail.status_code == 200
    assert detail.json()["data"]["question_count"] == 1
    assert detail.json()["data"]["questions"] == []
    assert "SECRET" not in detail.text
    listed = client.get("/assessment/assessments", headers=student)
    assert assessment_id in listed.text
    assert "SECRET" not in listed.text
    # Counted in SQL: the question rows aren't loaded for a mobile read.
    [item] = [a for a in listed.json()["data"] if a["id"] == assessment_id]
    assert (item["question_count"], item["questions"]) == (1, [])


@pytest.mark.asyncio
async def test_staff_see_the_questions_only_on_their_own_route(client):
    # M3-E decision 2: the mobile routes never return questions, to anyone.
    lecturer, _, assessment_id, _ = await assessment_with_question(client, published=True)
    mobile = client.get(f"/assessment/assessments/{assessment_id}", headers=lecturer)
    assert mobile.json()["data"]["questions"] == [] and "SECRET" not in mobile.text
    detail = client.get(f"/assessment/staff/assessments/{assessment_id}", headers=lecturer)
    assert detail.json()["data"]["questions"][0]["prompt"] == "SECRET-PROMPT"


@pytest.mark.asyncio
async def test_another_tenants_student_and_staff_get_not_found(client):
    _, _, assessment_id, question_id = await assessment_with_question(client, published=True)
    other_lecturer, other_student, _, _ = await assessment_with_question(client, published=True)
    for other in (other_student, other_lecturer):
        assert client.get(f"/assessment/assessments/{assessment_id}", headers=other).status_code == 404
        assert assessment_id not in client.get("/assessment/assessments", headers=other).text
    assert client.get(f"/assessment/questions/{question_id}", headers=other_lecturer).status_code == 404


@pytest.mark.asyncio
async def test_someone_outside_the_tenant_is_refused(client):
    _, student, assessment_id, _ = await assessment_with_question(client, published=True)
    _, outsider_token = await register_and_authenticate(client, f"vis-outsider-{uuid4()}@example.com")
    outsider = headers(outsider_token, student["X-Tenant-Slug"])
    assert client.get(f"/assessment/assessments/{assessment_id}", headers=outsider).status_code == 403
    assert client.get("/assessment/assessments", headers=outsider).status_code == 403


@pytest.mark.asyncio
async def test_a_student_cannot_read_the_answer_key_during_an_attempt(client):
    _, student, assessment_id, _ = await assessment_with_question(client, published=True)
    started = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["id"]
    questions = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student)
    assert "is_correct" not in questions.text
    question_id = questions.json()["data"]["questions"][0]["question_id"]

    question = client.get(f"/assessment/questions/{question_id}", headers=student)
    assert question.status_code == 403
    assert "SECRET" not in question.text
    assert "is_correct" not in question.text


@pytest.mark.asyncio
async def test_staff_can_still_read_a_question(client):
    lecturer, _, _, question_id = await assessment_with_question(client, published=False)
    question = client.get(f"/assessment/questions/{question_id}", headers=lecturer)
    assert question.status_code == 200
    assert question.json()["data"]["options"][1]["is_correct"] is True


# --- M3-E: staff routes, and hidden courses ---------------------------------------------


async def hide(level: str, assessment_id: str, client, lecturer) -> None:
    """Archive the assessment's course, or the department or faculty above it."""
    from sqlalchemy import select, update

    from app.db.session import SessionLocal
    from app.infrastructure.db.models.catalogue import CourseModel
    from app.infrastructure.db.models.tenant_core import DepartmentModel

    course_id = client.get(f"/assessment/staff/assessments/{assessment_id}", headers=lecturer).json()["data"]["course_id"]
    async with SessionLocal() as session, session.begin():
        if level == "course":
            await session.execute(update(CourseModel).where(CourseModel.id == course_id).values(status="archived"))
            return
        department_id = await session.scalar(select(CourseModel.department_id).where(CourseModel.id == course_id))
        if level == "department":
            await session.execute(update(DepartmentModel).where(DepartmentModel.id == department_id).values(status="archived"))
            return
        from app.infrastructure.db.models.tenant_core import FacultyModel

        faculty_id = await session.scalar(select(DepartmentModel.faculty_id).where(DepartmentModel.id == department_id))
        await session.execute(update(FacultyModel).where(FacultyModel.id == faculty_id).values(status="archived"))


@pytest.mark.asyncio
async def test_the_staff_routes_need_assessment_update(client):
    lecturer, student, assessment_id, _ = await assessment_with_question(client, published=False)
    assert client.get("/assessment/staff/assessments", headers=student).status_code == 403
    assert client.get(f"/assessment/staff/assessments/{assessment_id}", headers=student).status_code == 403
    assert client.get(f"/assessment/staff/assessments/{uuid4()}", headers=lecturer).status_code == 404


@pytest.mark.asyncio
async def test_the_staff_list_filters_by_status(client):
    lecturer, _, draft_id, _ = await assessment_with_question(client, published=False)
    drafts = client.get("/assessment/staff/assessments", headers=lecturer, params={"status": "draft"})
    published = client.get("/assessment/staff/assessments", headers=lecturer, params={"status": "published"})
    assert draft_id in drafts.text and draft_id not in published.text
    assert client.get("/assessment/staff/assessments", headers=lecturer, params={"status": "nonsense"}).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["course", "department", "faculty"])
async def test_a_hidden_course_hides_its_assessments_and_refuses_new_attempts_for_everyone(client, level):
    lecturer, student, assessment_id, _ = await assessment_with_question(client, published=True)
    await hide(level, assessment_id, client, lecturer)
    for caller in (student, lecturer):
        assert assessment_id not in client.get("/assessment/assessments", headers=caller).text
        assert client.get(f"/assessment/assessments/{assessment_id}", headers=caller).status_code == 404
    started = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    # The same refusal as a draft: not available for attempts.
    assert started.status_code == 409, started.text
    # Staff still find it on their own route, for authoring.
    assert client.get(f"/assessment/staff/assessments/{assessment_id}", headers=lecturer).status_code == 200


@pytest.mark.asyncio
async def test_an_attempt_in_progress_survives_its_course_being_archived(client):
    lecturer, student, assessment_id, _ = await assessment_with_question(client, published=True)
    started = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["id"]
    await hide("course", assessment_id, client, lecturer)
    # Decision 4: no student loses work they started.
    assert client.get(f"/assessment/attempts/{attempt_id}", headers=student).status_code == 200
    submitted = client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student)
    assert submitted.status_code == 200, submitted.text
    assert attempt_id in client.get("/assessment/attempts", headers=student).text

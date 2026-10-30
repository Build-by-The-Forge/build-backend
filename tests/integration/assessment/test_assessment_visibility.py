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
    assert draft_id in client.get("/assessment/assessments", headers=lecturer).text


@pytest.mark.asyncio
async def test_a_student_list_by_course_excludes_drafts(client):
    lecturer, student, draft_id, _ = await assessment_with_question(client, published=False)
    course_id = client.get(f"/assessment/assessments/{draft_id}", headers=lecturer).json()["data"]["course_id"]
    listed = client.get("/assessment/assessments", headers=student, params={"course_id": course_id})
    assert listed.status_code == 200
    assert draft_id not in listed.text


@pytest.mark.asyncio
async def test_a_draft_by_direct_id_looks_like_it_does_not_exist(client):
    lecturer, student, draft_id, _ = await assessment_with_question(client, published=False)
    draft = client.get(f"/assessment/assessments/{draft_id}", headers=student)
    missing = client.get(f"/assessment/assessments/{uuid4()}", headers=student)
    assert draft.status_code == missing.status_code == 404
    assert draft.json()["meta"] == missing.json()["meta"]
    assert "SECRET" not in draft.text
    assert client.get(f"/assessment/assessments/{draft_id}", headers=lecturer).json()["data"]["status"] == "draft"


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


@pytest.mark.asyncio
async def test_staff_still_see_the_questions(client):
    lecturer, _, assessment_id, _ = await assessment_with_question(client, published=True)
    detail = client.get(f"/assessment/assessments/{assessment_id}", headers=lecturer)
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

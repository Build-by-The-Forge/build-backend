"""Submitting an attempt reports its outcomes to learning memory (M5 R3).

AI-service is a recording gateway here; the real path is in the boundary
suite (M5-4).
"""

from uuid import uuid4

from app.api.ai import get_ai_assistant_gateway
from app.domain.ai.assistant import AIAssistantError
from app.main import app
from tests.integration.ai.test_ai_api import RecordingGateway
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


async def published_assessment(client, n_questions: int):
    lecturer_id, token = await register_and_authenticate(client, f"mem-lect-{uuid4()}@example.com")
    tenant_id, slug, topic_id, outcome_id = await seed_tenant_context(lecturer_id, "lecturer")
    h = headers(token, slug)
    from tests.integration.assessment.test_assessment_api import course_id_for_tenant

    created = client.post(
        "/assessment/assessments",
        headers=h,
        json={
            "course_id": await course_id_for_tenant(tenant_id),
            "title": "Memory",
            "instructions": "x",
            "duration_minutes": 30,
        },
    )
    assessment_id = created.json()["data"]["id"]
    for i in range(n_questions):
        question = client.post(
            "/assessment/questions",
            headers=h,
            json={
                "topic_id": topic_id,
                "learning_outcome_id": outcome_id,
                "question_type": "mcq",
                "prompt": f"Q{i}?",
                "options": [
                    {"text": "Wrong", "display_order": 1, "is_correct": False},
                    {"text": "Right", "display_order": 2, "is_correct": True},
                ],
            },
        )
        added = client.post(
            f"/assessment/assessments/{assessment_id}/questions",
            headers=h,
            json={"question_id": question.json()["data"]["id"]},
        )
        assert added.status_code == 200, added.text
    assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=h).status_code == 200
    return tenant_id, slug, assessment_id


async def student_attempt(client, tenant_id, slug, assessment_id):
    student_id, token = await register_and_authenticate(client, f"mem-stu-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    h = headers(token, slug)
    started = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=h)
    attempt_id = started.json()["data"]["id"]
    delivered = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=h)
    return student_id, h, attempt_id, delivered.json()["data"]["questions"]


def answer(client, h, attempt_id, question, position):
    response = client.put(
        f"/assessment/attempts/{attempt_id}/answers/{question['assessment_question_id']}",
        json={"selected_option_index": position},
        headers=h,
    )
    assert response.status_code in (200, 201), response.text


async def test_a_submitted_attempt_updates_the_students_memory(client):
    recorder = RecordingGateway()
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: recorder
    try:
        tenant_id, slug, assessment_id = await published_assessment(client, 3)
        student_id, h, attempt_id, questions = await student_attempt(client, tenant_id, slug, assessment_id)
        answer(client, h, attempt_id, questions[0], 1)  # right
        answer(client, h, attempt_id, questions[1], 0)  # wrong
        # questions[2] is left unanswered and is not reported.
        assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=h).status_code == 200
    finally:
        app.dependency_overrides.pop(get_ai_assistant_gateway, None)

    [(name, actor, (observations,))] = recorder.calls
    assert name == "record_memory"
    assert (actor.tenant_id, actor.user_id, actor.role) == (tenant_id, student_id, "student")
    assert actor.permission == "assessment.attempt.submit"
    assert sorted((o.topic, o.correct) for o in observations) == [
        ("Assessment Topic", False),
        ("Assessment Topic", True),
    ]


async def test_an_ai_service_failure_never_fails_the_submission(client):
    failing = RecordingGateway(AIAssistantError("down", error_code="AI_SERVICE_UNAVAILABLE", unavailable=True))
    app.dependency_overrides[get_ai_assistant_gateway] = lambda: failing
    try:
        tenant_id, slug, assessment_id = await published_assessment(client, 1)
        _, h, attempt_id, questions = await student_attempt(client, tenant_id, slug, assessment_id)
        answer(client, h, attempt_id, questions[0], 1)
        submitted = client.post(f"/assessment/attempts/{attempt_id}/submit", headers=h)
    finally:
        app.dependency_overrides.pop(get_ai_assistant_gateway, None)
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "submitted"
    assert [call[0] for call in failing.calls] == ["record_memory"]

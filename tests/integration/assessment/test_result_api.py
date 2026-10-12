from uuid import uuid4

import pytest

from tests.integration.assessment.test_assessment_api import course_id_for_tenant
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


@pytest.mark.asyncio
async def test_attempt_result_api_flow_and_security(client) -> None:
    # 1. Lecturer creates course assessment with 2 questions
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"result-lecturer-{uuid4()}@example.com")
    tenant_id, tenant_slug, topic_id, learning_outcome_id = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer_headers = headers(lecturer_token, tenant_slug)

    course_id = await course_id_for_tenant(tenant_id)
    assessment = client.post(
        "/assessment/assessments",
        headers=lecturer_headers,
        json={
            "course_id": course_id,
            "title": "Algorithms Exam",
            "instructions": "Answer all questions.",
            "duration_minutes": 30,
            "passing_score": 5,
        },
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["data"]["id"]

    q1 = client.post(
        "/assessment/questions",
        headers=lecturer_headers,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": learning_outcome_id,
            "question_type": "mcq",
            "prompt": "Which is FIFO?",
            "marks": 5,
            "options": [
                {"text": "Stack", "display_order": 1, "is_correct": False},
                {"text": "Queue", "display_order": 2, "is_correct": True},
            ],
        },
    )
    assert q1.status_code == 201, q1.text
    q1_id = q1.json()["data"]["id"]

    q2 = client.post(
        "/assessment/questions",
        headers=lecturer_headers,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": learning_outcome_id,
            "question_type": "mcq",
            "prompt": "Which is LIFO?",
            "marks": 5,
            "options": [
                {"text": "Stack", "display_order": 1, "is_correct": True},
                {"text": "Queue", "display_order": 2, "is_correct": False},
            ],
        },
    )
    assert q2.status_code == 201, q2.text
    q2_id = q2.json()["data"]["id"]

    client.post(
        f"/assessment/assessments/{assessment_id}/questions",
        headers=lecturer_headers,
        json={"question_id": q1_id},
    )
    client.post(
        f"/assessment/assessments/{assessment_id}/questions",
        headers=lecturer_headers,
        json={"question_id": q2_id},
    )
    client.post(
        f"/assessment/assessments/{assessment_id}/publish",
        headers=lecturer_headers,
    )

    # 2. Student 1 starts attempt
    student1_id, student1_token = await register_and_authenticate(client, f"student1-{uuid4()}@example.com")
    await add_membership(student1_id, tenant_id, "student")
    student1_headers = headers(student1_token, tenant_slug)

    attempt_res = client.post(
        f"/assessment/assessments/{assessment_id}/attempts",
        headers=student1_headers,
    )
    assert attempt_res.status_code == 201, attempt_res.text
    attempt_id = attempt_res.json()["data"]["id"]

    # 3. Before submit, check getting result returns 409 Conflict
    unsubmitted_result = client.get(
        f"/assessment/attempts/{attempt_id}/result",
        headers=student1_headers,
    )
    assert unsubmitted_result.status_code == 409, unsubmitted_result.text

    # 4. Student 1 fetches questions
    questions_res = client.get(
        f"/assessment/attempts/{attempt_id}/questions",
        headers=student1_headers,
    )
    assert questions_res.status_code == 200
    q_data = questions_res.json()["data"]["questions"]
    aq1_id = q_data[0]["assessment_question_id"]

    # Answer Q1 correctly (index 1 = Queue), leave Q2 unanswered
    save_ans = client.put(
        f"/assessment/attempts/{attempt_id}/answers/{aq1_id}",
        headers=student1_headers,
        json={"selected_option_index": 1},
    )
    assert save_ans.status_code == 200

    # 5. Submit attempt
    submit_res = client.post(
        f"/assessment/attempts/{attempt_id}/submit",
        headers=student1_headers,
    )
    assert submit_res.status_code == 200, submit_res.text

    # 6. Read result as Student 1
    result_res = client.get(
        f"/assessment/attempts/{attempt_id}/result",
        headers=student1_headers,
    )
    assert result_res.status_code == 200, result_res.text
    result_data = result_res.json()["data"]

    assert result_data["total_score"] == 5
    assert result_data["max_score"] == 10
    assert result_data["percentage"] == 50.0
    assert result_data["passed"] is True  # 5 >= passing_score 5
    assert len(result_data["breakdown"]) == 2

    # Verify zero answer key leakage in response!
    for item in result_data["breakdown"]:
        assert "correct_option_index" not in item

    # 7. Student 2 cannot access Student 1's result
    student2_id, student2_token = await register_and_authenticate(client, f"student2-{uuid4()}@example.com")
    await add_membership(student2_id, tenant_id, "student")
    student2_headers = headers(student2_token, tenant_slug)

    student2_result = client.get(
        f"/assessment/attempts/{attempt_id}/result",
        headers=student2_headers,
    )
    assert student2_result.status_code == 404

    # 8. Lecturer can read Student 1's result
    lecturer_result = client.get(
        f"/assessment/attempts/{attempt_id}/result",
        headers=lecturer_headers,
    )
    assert lecturer_result.status_code == 200
    assert lecturer_result.json()["data"]["total_score"] == 5

    # 9. Cross-tenant isolation check
    other_tenant_id, other_tenant_slug, _, _ = await seed_tenant_context(student1_id, "student")
    other_headers = headers(student1_token, other_tenant_slug)
    cross_tenant_res = client.get(
        f"/assessment/attempts/{attempt_id}/result",
        headers=other_headers,
    )
    assert cross_tenant_res.status_code == 404

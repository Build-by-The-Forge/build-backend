from uuid import uuid4

import pytest
from tests.integration.assessment.test_assessment_api import course_id_for_tenant
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import (
    register_and_authenticate,
    seed_tenant_context,
)


@pytest.mark.asyncio
async def test_staff_assessment_gradebook_and_results_api(client) -> None:
    # 1. Lecturer creates course assessment with 1 question
    lecturer_id, lecturer_token = await register_and_authenticate(
        client, f"gradebook-lecturer-{uuid4()}@example.com"
    )
    tenant_id, tenant_slug, topic_id, learning_outcome_id = await seed_tenant_context(
        lecturer_id, "lecturer"
    )
    lecturer_headers = headers(lecturer_token, tenant_slug)

    course_id = await course_id_for_tenant(tenant_id)
    assessment = client.post(
        "/assessment/assessments",
        headers=lecturer_headers,
        json={
            "course_id": course_id,
            "title": "Gradebook Midterm",
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
            "prompt": "What is 2+2?",
            "marks": 5,
            "options": [
                {"text": "3", "display_order": 1, "is_correct": False},
                {"text": "4", "display_order": 2, "is_correct": True},
            ],
        },
    )
    assert q1.status_code == 201
    q1_id = q1.json()["data"]["id"]

    client.post(
        f"/assessment/assessments/{assessment_id}/questions",
        headers=lecturer_headers,
        json={"question_id": q1_id},
    )
    client.post(
        f"/assessment/assessments/{assessment_id}/publish",
        headers=lecturer_headers,
    )

    # 2. Student 1 starts and submits attempt (correct answer -> 5 marks)
    s1_id, s1_token = await register_and_authenticate(
        client, f"student1-{uuid4()}@example.com"
    )
    await add_membership(s1_id, tenant_id, "student")
    s1_headers = headers(s1_token, tenant_slug)

    att1 = client.post(
        f"/assessment/assessments/{assessment_id}/attempts",
        headers=s1_headers,
    ).json()["data"]
    att1_id = att1["id"]

    q_list = client.get(
        f"/assessment/attempts/{att1_id}/questions",
        headers=s1_headers,
    ).json()["data"]["questions"]
    aq1_id = q_list[0]["assessment_question_id"]

    # Student 1 answers correctly (index 1) and submits
    client.put(
        f"/assessment/attempts/{att1_id}/answers/{aq1_id}",
        headers=s1_headers,
        json={"selected_option_index": 1},
    )
    client.post(f"/assessment/attempts/{att1_id}/submit", headers=s1_headers)

    # 3. Student 2 starts and submits attempt (incorrect answer -> 0 marks)
    s2_id, s2_token = await register_and_authenticate(
        client, f"student2-{uuid4()}@example.com"
    )
    await add_membership(s2_id, tenant_id, "student")
    s2_headers = headers(s2_token, tenant_slug)

    att2 = client.post(
        f"/assessment/assessments/{assessment_id}/attempts",
        headers=s2_headers,
    ).json()["data"]
    att2_id = att2["id"]

    client.put(
        f"/assessment/attempts/{att2_id}/answers/{aq1_id}",
        headers=s2_headers,
        json={"selected_option_index": 0},
    )
    client.post(f"/assessment/attempts/{att2_id}/submit", headers=s2_headers)

    # 4. Student 3 starts attempt but DOES NOT submit (in progress)
    s3_id, s3_token = await register_and_authenticate(
        client, f"student3-{uuid4()}@example.com"
    )
    await add_membership(s3_id, tenant_id, "student")
    s3_headers = headers(s3_token, tenant_slug)

    client.post(
        f"/assessment/assessments/{assessment_id}/attempts",
        headers=s3_headers,
    )

    # 5. Lecturer queries assessment gradebook (200 OK)
    gradebook_res = client.get(
        f"/assessment/assessments/{assessment_id}/results?limit=10&offset=0",
        headers=lecturer_headers,
    )
    assert gradebook_res.status_code == 200, gradebook_res.text
    body = gradebook_res.json()
    assert body["success"] is True
    assert body["meta"]["total"] == 2  # Only submitted/graded attempts!
    assert body["meta"]["limit"] == 10
    assert body["meta"]["offset"] == 0

    results = body["data"]["results"]
    assert len(results) == 2
    user_ids = {r["user_id"] for r in results}
    assert s1_id in user_ids
    assert s2_id in user_ids
    assert s3_id not in user_ids  # In-progress attempt excluded!

    # 6. Pagination check (limit=1)
    p1 = client.get(
        f"/assessment/assessments/{assessment_id}/results?limit=1&offset=0",
        headers=lecturer_headers,
    ).json()
    assert p1["meta"]["total"] == 2
    assert len(p1["data"]["results"]) == 1

    p2 = client.get(
        f"/assessment/assessments/{assessment_id}/results?limit=1&offset=1",
        headers=lecturer_headers,
    ).json()
    assert p2["meta"]["total"] == 2
    assert len(p2["data"]["results"]) == 1
    assert p1["data"]["results"][0]["attempt_id"] != p2["data"]["results"][0]["attempt_id"]

    # 7. Student caller is FORBIDDEN (403)
    student_res = client.get(
        f"/assessment/assessments/{assessment_id}/results",
        headers=s1_headers,
    )
    assert student_res.status_code == 403

    # 8. Cross-tenant lecturer cannot see foreign assessment (404)
    other_lecturer_id, other_token = await register_and_authenticate(
        client, f"other-lecturer-{uuid4()}@example.com"
    )
    _, other_slug, _, _ = await seed_tenant_context(other_lecturer_id, "lecturer")
    other_headers = headers(other_token, other_slug)

    cross_res = client.get(
        f"/assessment/assessments/{assessment_id}/results",
        headers=other_headers,
    )
    assert cross_res.status_code == 404

    # 9. Non-existent assessment returns 404
    non_existent = client.get(
        "/assessment/assessments/non-existent-id/results",
        headers=lecturer_headers,
    )
    assert non_existent.status_code == 404

    # 10. Parameter validation (422 for invalid limit/offset)
    invalid_limit = client.get(
        f"/assessment/assessments/{assessment_id}/results?limit=0",
        headers=lecturer_headers,
    )
    assert invalid_limit.status_code == 422

    invalid_offset = client.get(
        f"/assessment/assessments/{assessment_id}/results?offset=-1",
        headers=lecturer_headers,
    )
    assert invalid_offset.status_code == 422

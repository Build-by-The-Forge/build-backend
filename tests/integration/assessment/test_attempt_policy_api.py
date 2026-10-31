"""The attempt policy over HTTP: staff set it, it locks at publication, and the
server enforces it when a student starts an attempt."""

from datetime import timedelta
from uuid import uuid4

import pytest

from tests.integration.assessment.test_assessment_api import course_id_for_tenant
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_attempt_deadline import move_deadline, result_rows
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context

ONE_ATTEMPT = {
    "kind": "formal",
    "max_attempts": 1,
    "retake_after_submission": False,
    "result_visibility": "after_release",
    "feedback_timing": "never",
    "scoring_policy": "first",
}
TWO_ATTEMPTS = {**ONE_ATTEMPT, "max_attempts": 2, "retake_after_submission": True, "scoring_policy": "latest"}
PRACTICE_DEFAULTS = {
    "kind": "practice",
    "max_attempts": None,
    "retake_after_submission": True,
    "result_visibility": "immediate",
    "feedback_timing": "immediate",
    "scoring_policy": "best",
}


async def lecturer_and_draft(client, policy=None):
    lecturer_id, token = await register_and_authenticate(client, f"pol-lect-{uuid4()}@example.com")
    tenant_id, slug, topic_id, outcome_id = await seed_tenant_context(lecturer_id, "lecturer")
    h = headers(token, slug)
    body = {
        "course_id": await course_id_for_tenant(tenant_id),
        "title": "Policy",
        "instructions": "Answer.",
        "duration_minutes": 30,
    }
    if policy is not None:
        body["attempt_policy"] = policy
    created = client.post("/assessment/assessments", headers=h, json=body)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["data"]["id"]
    question = client.post(
        "/assessment/questions",
        headers=h,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": outcome_id,
            "question_type": "mcq",
            "prompt": "Q?",
            "options": [
                {"text": "Wrong", "display_order": 1, "is_correct": False},
                {"text": "Right", "display_order": 2, "is_correct": True},
            ],
        },
    )
    added = client.post(
        f"/assessment/assessments/{assessment_id}/questions", headers=h, json={"question_id": question.json()["data"]["id"]}
    )
    assert added.status_code == 200, added.text
    return h, tenant_id, slug, assessment_id


async def published_with_student(client, policy):
    h, tenant_id, slug, assessment_id = await lecturer_and_draft(client, policy)
    assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=h).status_code == 200
    student_id, token = await register_and_authenticate(client, f"pol-stu-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    return headers(token, slug), assessment_id


def start(client, h, assessment_id):
    return client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=h)


def submit(client, h, attempt_id):
    response = client.post(f"/assessment/attempts/{attempt_id}/submit", headers=h)
    assert response.status_code == 200, response.text


async def test_an_assessment_without_a_policy_gets_the_practice_defaults(client):
    h, _, _, assessment_id = await lecturer_and_draft(client)
    data = client.get(f"/assessment/assessments/{assessment_id}", headers=h).json()["data"]
    assert data["attempt_policy"] == PRACTICE_DEFAULTS


async def test_practice_defaults_never_limit_retakes(client):
    student, assessment_id = await published_with_student(client, None)
    for _ in range(4):
        started = start(client, student, assessment_id)
        assert started.status_code == 201, started.text
        submit(client, student, started.json()["data"]["id"])


@pytest.mark.parametrize(
    "broken",
    [
        {**ONE_ATTEMPT, "retake_after_submission": True},
        {**ONE_ATTEMPT, "max_attempts": None},
        {**ONE_ATTEMPT, "max_attempts": 2},
        {**ONE_ATTEMPT, "max_attempts": 0},
        {**PRACTICE_DEFAULTS, "feedback_timing": "after_final_attempt"},
        {**ONE_ATTEMPT, "kind": "exam"},
        {**ONE_ATTEMPT, "scoring_policy": "average"},
        {k: v for k, v in ONE_ATTEMPT.items() if k != "kind"},
        {**ONE_ATTEMPT, "extra": 1},
    ],
)
async def test_a_contradictory_policy_is_refused_and_nothing_is_created(client, broken):
    lecturer_id, token = await register_and_authenticate(client, f"pol-lect-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(lecturer_id, "lecturer")
    h = headers(token, slug)
    response = client.post(
        "/assessment/assessments",
        headers=h,
        json={
            "course_id": await course_id_for_tenant(tenant_id),
            "title": "Bad",
            "instructions": "x",
            "duration_minutes": 30,
            "attempt_policy": broken,
        },
    )
    assert response.status_code == 422
    assert client.get("/assessment/assessments", headers=h).json()["data"] == []


async def test_a_draft_policy_can_change_until_publication_then_locks(client):
    h, _, _, assessment_id = await lecturer_and_draft(client)
    path = f"/assessment/assessments/{assessment_id}"
    changed = client.patch(path, headers=h, json={"attempt_policy": TWO_ATTEMPTS})
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["attempt_policy"] == TWO_ATTEMPTS

    assert client.post(f"{path}/publish", headers=h).status_code == 200

    locked = client.patch(path, headers=h, json={"attempt_policy": ONE_ATTEMPT, "title": "Changed"})
    assert locked.status_code == 409
    after = client.get(path, headers=h).json()["data"]
    assert after["attempt_policy"] == TWO_ATTEMPTS
    assert after["title"] == "Policy"
    # Resending the same policy is refused too: publication ends the question.
    assert client.patch(path, headers=h, json={"attempt_policy": TWO_ATTEMPTS}).status_code == 409


async def test_a_student_cannot_set_a_policy(client):
    student, assessment_id = await published_with_student(client, ONE_ATTEMPT)
    denied = client.patch(f"/assessment/assessments/{assessment_id}", headers=student, json={"attempt_policy": TWO_ATTEMPTS})
    assert denied.status_code == 403


async def test_a_student_sees_the_policy_and_their_own_count(client):
    student, assessment_id = await published_with_student(client, TWO_ATTEMPTS)
    path = f"/assessment/assessments/{assessment_id}"
    first = client.get(path, headers=student).json()["data"]
    assert first["attempt_policy"] == TWO_ATTEMPTS
    assert first["attempts_used"] == 0

    start(client, student, assessment_id)
    assert client.get(path, headers=student).json()["data"]["attempts_used"] == 1
    [listed] = [a for a in client.get("/assessment/assessments", headers=student).json()["data"] if a["id"] == assessment_id]
    assert listed["attempts_used"] == 1


async def test_one_attempt_means_one(client):
    student, assessment_id = await published_with_student(client, ONE_ATTEMPT)
    started = start(client, student, assessment_id)
    assert started.status_code == 201
    submit(client, student, started.json()["data"]["id"])

    refused = start(client, student, assessment_id)
    assert refused.status_code == 409
    assert "ATTEMPT_LIMIT_REACHED" in refused.text


async def test_a_limit_allows_retakes_up_to_it_and_no_further(client):
    student, assessment_id = await published_with_student(client, TWO_ATTEMPTS)
    for _ in range(2):
        started = start(client, student, assessment_id)
        assert started.status_code == 201, started.text
        submit(client, student, started.json()["data"]["id"])
    assert start(client, student, assessment_id).status_code == 409


async def test_starting_while_one_is_in_progress_returns_it_even_at_the_limit(client):
    student, assessment_id = await published_with_student(client, ONE_ATTEMPT)
    first = start(client, student, assessment_id).json()["data"]["id"]
    again = start(client, student, assessment_id)
    assert again.status_code in (200, 201)
    assert again.json()["data"]["id"] == first


async def test_another_students_attempts_do_not_count(client):
    h, tenant_id, slug, assessment_id = await lecturer_and_draft(client, ONE_ATTEMPT)
    assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=h).status_code == 200
    students = []
    for _ in range(2):
        student_id, token = await register_and_authenticate(client, f"pol-stu-{uuid4()}@example.com")
        await add_membership(student_id, tenant_id, "student")
        students.append(headers(token, slug))

    submit(client, students[0], start(client, students[0], assessment_id).json()["data"]["id"])

    assert start(client, students[1], assessment_id).status_code == 201


async def test_an_expired_attempt_counts_and_is_finalized_with_a_result(client):
    student, assessment_id = await published_with_student(client, TWO_ATTEMPTS)
    first = start(client, student, assessment_id).json()["data"]["id"]
    await move_deadline(first, timedelta(minutes=-1))

    second = start(client, student, assessment_id)

    assert second.status_code == 201, second.text
    assert second.json()["data"]["id"] != first
    assert client.get(f"/assessment/attempts/{first}", headers=student).json()["data"]["status"] == "submitted"
    assert await result_rows(first) == 1


async def test_abandoning_an_attempt_past_the_limit_still_finalizes_it(client):
    # The refusal must not roll back the finalization that came before it.
    student, assessment_id = await published_with_student(client, ONE_ATTEMPT)
    only = start(client, student, assessment_id).json()["data"]["id"]
    await move_deadline(only, timedelta(minutes=-1))

    refused = start(client, student, assessment_id)

    assert refused.status_code == 409
    assert "ATTEMPT_LIMIT_REACHED" in refused.text
    assert client.get(f"/assessment/attempts/{only}", headers=student).json()["data"]["status"] == "submitted"
    assert await result_rows(only) == 1
    # And it stays refused, with one result, however often the student retries.
    assert start(client, student, assessment_id).status_code == 409
    assert await result_rows(only) == 1

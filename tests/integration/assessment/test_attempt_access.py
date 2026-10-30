"""Over real authenticated HTTP: an attempt belongs to one student in one
tenant, and nothing a student can reach carries the answer key early."""

from uuid import uuid4

import pytest

from tests.integration.assessment.test_assessment_visibility import assessment_with_question
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import register_and_authenticate

KEY_FIELDS = ("is_correct", "explanation", "correct_option")


def assert_no_answer_key(text: str) -> None:
    for field in KEY_FIELDS:
        assert field not in text, field


async def started(client):
    _, student, assessment_id, _ = await assessment_with_question(client, published=True)
    response = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    assert response.status_code == 201, response.text
    attempt_id = response.json()["data"]["id"]
    questions = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student)
    question_id = questions.json()["data"]["questions"][0]["assessment_question_id"]
    return student, assessment_id, attempt_id, question_id


async def classmate_of(client, student) -> dict[str, str]:
    """A second student in the first one's tenant."""
    tenant = client.get("/identity/tenant-context", headers=student)
    assert tenant.status_code == 200, tenant.text
    user_id, token = await register_and_authenticate(client, f"access-classmate-{uuid4()}@example.com")
    await add_membership(user_id, tenant.json()["data"]["tenant_id"], "student")
    return headers(token, student["X-Tenant-Slug"])


def attempt_requests(attempt_id: str, question_id: str) -> list[tuple[str, str, dict | None]]:
    path = f"/assessment/attempts/{attempt_id}"
    return [
        ("GET", path, None),
        ("GET", f"{path}/questions", None),
        ("GET", f"{path}/answers", None),
        ("PUT", f"{path}/answers/{question_id}", {"selected_option_index": 0}),
        ("DELETE", f"{path}/answers/{question_id}", None),
        ("POST", f"{path}/submit", None),
        ("GET", f"{path}/result", None),
    ]


@pytest.mark.asyncio
async def test_another_students_attempt_is_not_found_on_every_route(client):
    student, _, attempt_id, question_id = await started(client)
    classmate = await classmate_of(client, student)
    for method, path, body in attempt_requests(attempt_id, question_id):
        response = client.request(method, path, headers=classmate, json=body)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"
        assert "SECRET" not in response.text
    # None of that touched the owner's attempt.
    owner = client.get(f"/assessment/attempts/{attempt_id}", headers=student).json()["data"]
    assert owner["status"] == "in_progress"
    assert client.get(f"/assessment/attempts/{attempt_id}/answers", headers=student).json()["data"]["answers"] == []


@pytest.mark.asyncio
async def test_a_submitted_attempts_result_is_not_found_for_a_classmate(client):
    student, _, attempt_id, _ = await started(client)
    classmate = await classmate_of(client, student)
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student).status_code == 200
    assert client.get(f"/assessment/attempts/{attempt_id}/result", headers=classmate).status_code == 404


@pytest.mark.asyncio
async def test_another_tenants_student_is_not_found_on_every_route(client):
    _, _, attempt_id, question_id = await started(client)
    _, other_tenant_student, _, _ = await assessment_with_question(client, published=True)
    for method, path, body in attempt_requests(attempt_id, question_id):
        response = client.request(method, path, headers=other_tenant_student, json=body)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"
        assert "SECRET" not in response.text


@pytest.mark.asyncio
async def test_a_question_outside_the_attempt_cannot_be_answered(client):
    student, _, attempt_id, _ = await started(client)
    _, _, _, foreign_question = await started(client)
    for question_id in (foreign_question, str(uuid4())):
        path = f"/assessment/attempts/{attempt_id}/answers/{question_id}"
        response = client.put(path, headers=student, json={"selected_option_index": 0})
        assert response.status_code == 404, response.text
    answers = client.get(f"/assessment/attempts/{attempt_id}/answers", headers=student)
    assert answers.json()["data"]["answers"] == []


@pytest.mark.asyncio
async def test_questions_are_unreachable_before_starting_and_after_submitting(client):
    _, student, assessment_id, _ = await assessment_with_question(client, published=True)
    # Before starting: there is no attempt to use, and the assessment holds no questions.
    detail = client.get(f"/assessment/assessments/{assessment_id}", headers=student)
    assert detail.json()["data"]["questions"] == []
    assert client.get(f"/assessment/attempts/{uuid4()}/questions", headers=student).status_code == 404

    attempt_id = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student).status_code == 200
    after = client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student)
    assert after.status_code == 404
    assert "SECRET" not in after.text


@pytest.mark.asyncio
async def test_no_student_route_carries_the_key_before_submission(client):
    student, assessment_id, attempt_id, question_id = await started(client)
    path = f"/assessment/attempts/{attempt_id}"
    responses = [
        client.get("/assessment/assessments", headers=student),
        client.get(f"/assessment/assessments/{assessment_id}", headers=student),
        client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student),
        client.get("/assessment/attempts", headers=student),
        client.get(path, headers=student),
        client.get(f"{path}/questions", headers=student),
        client.put(f"{path}/answers/{question_id}", headers=student, json={"selected_option_index": 0}),
        client.get(f"{path}/answers", headers=student),
        client.get(f"{path}/result", headers=student),
    ]
    for response in responses:
        assert response.status_code < 500, response.request.url
        assert_no_answer_key(response.text)


@pytest.mark.asyncio
async def test_the_result_never_carries_the_explanation(client):
    """is_correct is returned here today, which is gap G-36: it should wait for
    the feedback stage that arrives with attempt_policy."""
    student, _, attempt_id, _ = await started(client)
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student).status_code == 200
    result = client.get(f"/assessment/attempts/{attempt_id}/result", headers=student)
    assert result.status_code == 200
    assert "SECRET" not in result.text
    assert "explanation" not in result.text

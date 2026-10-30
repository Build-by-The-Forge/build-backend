"""The server's deadline on an attempt, and a safe repeated submit, over HTTP.

Policy: from expires_at onwards nothing can be saved or removed. Submitting
stays possible and grades what was saved in time, so a student who ran out of
time isn't left without a result.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.infrastructure.db.models.assessment import AssessmentAttemptModel, AssessmentAttemptResultModel
from tests.integration.assessment.test_assessment_api import course_id_for_tenant
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context


async def started_attempt(client, duration_minutes: int = 30):
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"dl-lecturer-{uuid4()}@example.com")
    tenant_id, slug, topic_id, outcome_id = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer = headers(lecturer_token, slug)
    assessment = client.post(
        "/assessment/assessments",
        headers=lecturer,
        json={
            "course_id": await course_id_for_tenant(tenant_id),
            "title": "Deadline",
            "instructions": "Answer all questions.",
            "duration_minutes": duration_minutes,
        },
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["data"]["id"]
    question = client.post(
        "/assessment/questions",
        headers=lecturer,
        json={
            "topic_id": topic_id,
            "learning_outcome_id": outcome_id,
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
        headers=lecturer,
        json={"question_id": question.json()["data"]["id"]},
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/assessment/assessments/{assessment_id}/publish", headers=lecturer).status_code == 200

    student_id, student_token = await register_and_authenticate(client, f"dl-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    student = headers(student_token, slug)
    started = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student)
    assert started.status_code == 201, started.text
    attempt = started.json()["data"]
    questions = client.get(f"/assessment/attempts/{attempt['id']}/questions", headers=student)
    return lecturer, student, assessment_id, attempt, questions.json()["data"]["questions"][0]["assessment_question_id"]


def moment(value: str) -> datetime:
    # SQLite drops the UTC offset on the way back from the database.
    return datetime.fromisoformat(value).replace(tzinfo=None)


async def move_deadline(attempt_id: str, delta: timedelta) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(AssessmentAttemptModel)
            .where(AssessmentAttemptModel.id == attempt_id)
            .values(expires_at=datetime.now(timezone.utc) + delta)
        )
        await session.commit()


async def result_rows(attempt_id: str) -> int:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(AssessmentAttemptResultModel).where(AssessmentAttemptResultModel.attempt_id == attempt_id)
        )
        return len(rows.all())


@pytest.mark.asyncio
async def test_the_deadline_is_the_start_time_plus_the_duration(client):
    _, _, _, attempt, _ = await started_attempt(client, duration_minutes=45)
    started = datetime.fromisoformat(attempt["started_at"])
    assert datetime.fromisoformat(attempt["expires_at"]) - started == timedelta(minutes=45)


@pytest.mark.asyncio
async def test_before_the_deadline_answers_save_and_submit_succeeds(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    path = f"/assessment/attempts/{attempt['id']}"
    saved = client.put(f"{path}/answers/{question_id}", headers=student, json={"selected_option_index": 1})
    assert saved.status_code == 200, saved.text
    submitted = client.post(f"{path}/submit", headers=student)
    assert submitted.status_code == 200
    assert client.get(f"{path}/result", headers=student).json()["data"]["total_score"] == 1


@pytest.mark.asyncio
async def test_after_the_deadline_an_answer_cannot_be_saved_or_removed(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    path = f"/assessment/attempts/{attempt['id']}/answers/{question_id}"
    assert client.put(path, headers=student, json={"selected_option_index": 0}).status_code == 200
    await move_deadline(attempt["id"], timedelta(seconds=-1))

    changed = client.put(path, headers=student, json={"selected_option_index": 1})
    assert changed.status_code == 409
    assert changed.json()["meta"]["error"] == "attempt expired"
    assert client.delete(path, headers=student).status_code == 409
    answers = client.get(f"/assessment/attempts/{attempt['id']}/answers", headers=student)
    assert answers.json()["data"]["answers"][0]["selected_option_index"] == 0


@pytest.mark.asyncio
async def test_submitting_after_the_deadline_grades_only_what_was_saved_in_time(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    path = f"/assessment/attempts/{attempt['id']}"
    await move_deadline(attempt["id"], timedelta(seconds=-1))
    assert client.put(f"{path}/answers/{question_id}", headers=student, json={"selected_option_index": 1}).status_code == 409

    submitted = client.post(f"{path}/submit", headers=student)
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "submitted"
    result = client.get(f"{path}/result", headers=student).json()["data"]
    assert result["total_score"] == 0
    assert result["max_score"] == 1


@pytest.mark.asyncio
async def test_the_client_has_no_way_to_extend_the_deadline(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    await move_deadline(attempt["id"], timedelta(seconds=-1))
    path = f"/assessment/attempts/{attempt['id']}/answers/{question_id}"

    claimed = client.put(
        path,
        headers={**student, "Date": "Thu, 01 Jan 2015 00:00:00 GMT", "X-Client-Time": "2015-01-01T00:00:00Z"},
        json={"selected_option_index": 1},
    )
    assert claimed.status_code == 409
    in_body = client.put(path, headers=student, json={"selected_option_index": 1, "expires_at": "2099-01-01T00:00:00Z"})
    assert in_body.status_code == 422
    assert client.put(path, headers=student, json={"selected_option_index": 1}).status_code == 409


@pytest.mark.asyncio
async def test_editing_the_assessment_does_not_move_a_running_attempts_deadline(client):
    lecturer, student, assessment_id, attempt, _ = await started_attempt(client, duration_minutes=30)
    edited = client.patch(f"/assessment/assessments/{assessment_id}", headers=lecturer, json={"duration_minutes": 600})
    after = client.get(f"/assessment/attempts/{attempt['id']}", headers=student).json()["data"]
    assert edited.status_code == 200, edited.text
    assert moment(after["expires_at"]) == moment(attempt["expires_at"])


@pytest.mark.asyncio
async def test_a_repeated_submit_returns_the_submitted_attempt_and_never_grades_again(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    path = f"/assessment/attempts/{attempt['id']}"
    assert client.put(f"{path}/answers/{question_id}", headers=student, json={"selected_option_index": 1}).status_code == 200
    first = client.post(f"{path}/submit", headers=student)
    result = client.get(f"{path}/result", headers=student).json()["data"]

    repeat = client.post(f"{path}/submit", headers=student)
    assert repeat.status_code == 200
    assert repeat.json()["data"]["status"] == "submitted"
    assert moment(repeat.json()["data"]["submitted_at"]) == moment(first.json()["data"]["submitted_at"])
    assert await result_rows(attempt["id"]) == 1
    assert client.get(f"{path}/result", headers=student).json()["data"] == result


@pytest.mark.asyncio
async def test_a_submitted_attempt_refuses_answers_as_already_submitted(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    path = f"/assessment/attempts/{attempt['id']}"
    assert client.post(f"{path}/submit", headers=student).status_code == 200
    late = client.put(f"{path}/answers/{question_id}", headers=student, json={"selected_option_index": 1})
    assert late.status_code == 409
    assert late.json()["meta"]["error"] == "attempt already submitted"

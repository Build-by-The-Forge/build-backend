"""An expired attempt gets finalized whether or not the student ever comes back:
by the worker with no client, and on any read if no worker has run yet."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app import worker
from app.db.session import SessionLocal
from app.infrastructure.db.models.assessment import AssessmentAttemptModel
from tests.integration.assessment.test_attempt_deadline import move_deadline, result_rows, started_attempt


@pytest.fixture(autouse=True)
def no_postgresql_timeouts(monkeypatch):
    # set_config doesn't exist on SQLite. The PostgreSQL gate runs the real one.
    async def nothing(session):
        return None

    monkeypatch.setattr(worker, "set_transaction_timeouts", nothing)


async def stored(attempt_id: str) -> AssessmentAttemptModel:
    # The database directly: going through a route would finalize it.
    async with SessionLocal() as session:
        return (await session.scalars(select(AssessmentAttemptModel).where(AssessmentAttemptModel.id == attempt_id))).one()


async def expired_attempt(client):
    _, student, assessment_id, attempt, question_id = await started_attempt(client)
    await move_deadline(attempt["id"], timedelta(minutes=-1))
    return student, assessment_id, attempt["id"], question_id


async def test_the_worker_finalizes_an_expired_attempt_with_no_client(client):
    _, _, attempt_id, _ = await expired_attempt(client)

    await worker.run_attempt_finalizer_pass()

    attempt = await stored(attempt_id)
    assert attempt.status == "submitted"
    assert attempt.finalized_by == "deadline"
    assert attempt.submitted_at is not None
    assert await result_rows(attempt_id) == 1


async def test_the_worker_leaves_a_running_attempt_alone(client):
    _, _, _, attempt, _ = await started_attempt(client)
    await worker.run_attempt_finalizer_pass()
    assert (await stored(attempt["id"])).status == "in_progress"
    assert await result_rows(attempt["id"]) == 0


async def test_the_worker_grades_saved_answers_and_scores_the_rest_zero(client):
    _, student, _, attempt, question_id = await started_attempt(client)
    saved = client.put(
        f"/assessment/attempts/{attempt['id']}/answers/{question_id}", json={"selected_option_index": 1}, headers=student
    )
    assert saved.status_code in (200, 201), saved.text
    await move_deadline(attempt["id"], timedelta(minutes=-1))

    await worker.run_attempt_finalizer_pass()

    assert client.get(f"/assessment/attempts/{attempt['id']}/result", headers=student).json()["data"]["total_score"] == 1


async def test_an_abandoned_attempt_with_no_answers_scores_zero(client):
    student, _, attempt_id, _ = await expired_attempt(client)
    await worker.run_attempt_finalizer_pass()
    assert client.get(f"/assessment/attempts/{attempt_id}/result", headers=student).json()["data"]["total_score"] == 0


async def test_a_later_pass_changes_nothing(client):
    _, _, attempt_id, _ = await expired_attempt(client)
    await worker.run_attempt_finalizer_pass()
    first = (await stored(attempt_id)).submitted_at
    await worker.run_attempt_finalizer_pass()
    assert (await stored(attempt_id)).submitted_at == first
    assert await result_rows(attempt_id) == 1


@pytest.mark.parametrize(
    "read",
    [
        lambda client, h, attempt_id: client.get(f"/assessment/attempts/{attempt_id}", headers=h),
        lambda client, h, attempt_id: client.get("/assessment/attempts", headers=h),
        lambda client, h, attempt_id: client.get(f"/assessment/attempts/{attempt_id}/questions", headers=h),
        lambda client, h, attempt_id: client.get(f"/assessment/attempts/{attempt_id}/result", headers=h),
    ],
    ids=["getAttempt", "listAttempts", "getAttemptQuestions", "getAttemptResult"],
)
async def test_every_read_finalizes_with_no_worker(client, read):
    student, _, attempt_id, _ = await expired_attempt(client)

    read(client, student, attempt_id)

    attempt = await stored(attempt_id)
    assert attempt.status == "submitted"
    assert attempt.finalized_by == "deadline"
    assert await result_rows(attempt_id) == 1


async def test_reads_show_it_finalized_and_refuse_its_questions(client):
    student, _, attempt_id, _ = await expired_attempt(client)
    assert client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student).status_code == 404
    assert client.get(f"/assessment/attempts/{attempt_id}", headers=student).json()["data"]["status"] == "submitted"
    assert await result_rows(attempt_id) == 1


async def test_a_read_of_a_running_attempt_changes_nothing(client):
    _, student, _, attempt, _ = await started_attempt(client)
    assert client.get(f"/assessment/attempts/{attempt['id']}", headers=student).json()["data"]["status"] == "in_progress"
    assert (await stored(attempt["id"])).status == "in_progress"


async def test_another_students_read_finalizes_nothing(client):
    student, _, attempt_id, _ = await expired_attempt(client)
    from uuid import uuid4

    from tests.integration.assessment.test_attempt_api import add_membership, headers
    from tests.integration.assessment.test_question_api import register_and_authenticate

    other_id, token = await register_and_authenticate(client, f"fin-other-{uuid4()}@example.com")
    attempt = await stored(attempt_id)
    await add_membership(other_id, attempt.tenant_id, "student")
    other = headers(token, student["X-Tenant-Slug"])

    assert client.get(f"/assessment/attempts/{attempt_id}", headers=other).status_code == 404
    assert (await stored(attempt_id)).status == "in_progress"


async def test_a_student_submitting_late_is_recorded_as_the_student(client):
    student, _, attempt_id, _ = await expired_attempt(client)
    assert client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student).status_code == 200
    assert (await stored(attempt_id)).finalized_by == "student"


async def test_a_refused_result_read_does_not_undo_its_finalization(client):
    from tests.integration.assessment.test_result_release_api import policy, published

    _, student, assessment_id = await published(client, policy("after_release"))
    attempt_id = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]
    await move_deadline(attempt_id, timedelta(minutes=-1))

    refused = client.get(f"/assessment/attempts/{attempt_id}/result", headers=student)

    assert refused.status_code == 409
    assert "RESULT_NOT_RELEASED" in refused.text
    assert (await stored(attempt_id)).status == "submitted"
    assert await result_rows(attempt_id) == 1


async def test_after_final_attempt_feedback_arrives_once_the_last_attempt_expires(client):
    from tests.integration.assessment.test_result_release_api import assert_feedback, assert_score_only, policy, published, take

    _, student, assessment_id = await published(client, policy("immediate", "after_final_attempt"))
    first = take(client, student, assessment_id)
    last = client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student).json()["data"]["id"]
    assert_score_only(client.get(f"/assessment/attempts/{first}/result", headers=student))

    await move_deadline(last, timedelta(minutes=-1))

    assert_feedback(client.get(f"/assessment/attempts/{first}/result", headers=student))
    assert await result_rows(last) == 1


async def test_one_attempt_that_cannot_finalize_does_not_stop_the_others(client, monkeypatch):
    _, _, poisoned, _ = await expired_attempt(client)
    _, _, healthy, _ = await expired_attempt(client)
    real = worker.finalize_attempt

    async def failing(*args, attempt_id, **kwargs):
        if attempt_id == poisoned:
            raise RuntimeError("grading failed")
        return await real(*args, attempt_id=attempt_id, **kwargs)

    monkeypatch.setattr(worker, "finalize_attempt", failing)
    await worker.run_attempt_finalizer_pass()

    assert (await stored(healthy)).status == "submitted"
    # Rolled back and still eligible.
    assert (await stored(poisoned)).status == "in_progress"
    monkeypatch.setattr(worker, "finalize_attempt", real)
    await worker.run_attempt_finalizer_pass()
    assert (await stored(poisoned)).status == "submitted"

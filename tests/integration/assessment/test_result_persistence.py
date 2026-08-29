import pytest
from app.domain.assessment.assessment import Assessment
from app.domain.assessment.result import AttemptResult, QuestionResult
from app.infrastructure.assessment.repositories import (
    SqlAlchemyAssessmentRepository,
    SqlAlchemyAttemptResultRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_attempt_result_round_trip(session: AsyncSession) -> None:
    qr = QuestionResult(
        assessment_question_id="aq-1",
        selected_option_index=1,
        correct_option_index=1,
        awarded_marks=5,
        max_marks=5,
        is_correct=True,
    )
    result = AttemptResult.create(
        tenant_id="tenant-123",
        attempt_id="attempt-123",
        assessment_id="assessment-123",
        user_id="user-123",
        total_score=5,
        max_score=5,
        percentage=100.0,
        passed=True,
        breakdown=[qr],
    )
    result.pull_events()

    repository = SqlAlchemyAttemptResultRepository(session)
    await repository.save(result)

    retrieved_by_attempt = await repository.get_by_attempt_id(
        "attempt-123", tenant_id="tenant-123"
    )
    assert retrieved_by_attempt is not None
    assert retrieved_by_attempt.id == result.id
    assert retrieved_by_attempt.total_score == 5
    assert retrieved_by_attempt.percentage == 100.0
    assert retrieved_by_attempt.passed is True
    assert len(retrieved_by_attempt.breakdown) == 1
    assert retrieved_by_attempt.breakdown[0].is_correct is True

    retrieved_by_id = await repository.get_by_id(result.id, tenant_id="tenant-123")
    assert retrieved_by_id is not None
    assert retrieved_by_id.attempt_id == "attempt-123"


@pytest.mark.asyncio
async def test_attempt_result_tenant_isolation(session: AsyncSession) -> None:
    result = AttemptResult.create(
        tenant_id="tenant-123",
        attempt_id="attempt-123",
        assessment_id="assessment-123",
        user_id="user-123",
        total_score=3,
        max_score=5,
        percentage=60.0,
        passed=True,
    )
    result.pull_events()
    repository = SqlAlchemyAttemptResultRepository(session)
    await repository.save(result)

    assert (
        await repository.get_by_attempt_id("attempt-123", tenant_id="tenant-999")
        is None
    )
    assert await repository.get_by_id(result.id, tenant_id="tenant-999") is None
    assert len(await repository.list_by_user("user-123", tenant_id="tenant-999")) == 0


@pytest.mark.asyncio
async def test_assessment_question_snapshot_correct_option_index_persistence(
    session: AsyncSession,
) -> None:
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Test Exam",
        instructions="Instructions",
        duration_minutes=30,
        passing_score=5,
    )
    assessment.add_question(
        question_id="q-1",
        prompt="Prompt",
        options=["A", "B", "C"],
        marks=2,
        correct_option_index=2,
    )
    assessment_repo = SqlAlchemyAssessmentRepository(session)
    await assessment_repo.save(assessment, tenant_id="tenant-123")

    snapshots = await assessment_repo.list_question_snapshots(
        assessment.id, tenant_id="tenant-123"
    )
    assert len(snapshots) == 1
    assert snapshots[0].correct_option_index == 2

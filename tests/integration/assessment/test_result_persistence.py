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


@pytest.mark.asyncio
async def test_list_by_assessment_pagination_and_isolation(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyAttemptResultRepository(session)
    for i in range(5):
        res = AttemptResult.create(
            tenant_id="tenant-100",
            attempt_id=f"attempt-100-{i}",
            assessment_id="assessment-100",
            user_id=f"user-{i}",
            total_score=i * 2,
            max_score=10,
            percentage=float(i * 20),
            passed=i >= 3,
        )
        res.pull_events()
        await repository.save(res)

    # Different tenant / assessment
    other_res = AttemptResult.create(
        tenant_id="tenant-200",
        attempt_id="attempt-other",
        assessment_id="assessment-100",
        user_id="user-other",
        total_score=10,
        max_score=10,
        percentage=100.0,
        passed=True,
    )
    other_res.pull_events()
    await repository.save(other_res)

    # Page 1 (limit 2, offset 0)
    page1, total = await repository.list_by_assessment(
        "assessment-100", tenant_id="tenant-100", limit=2, offset=0
    )
    assert total == 5
    assert len(page1) == 2

    # Page 2 (limit 2, offset 2)
    page2, total2 = await repository.list_by_assessment(
        "assessment-100", tenant_id="tenant-100", limit=2, offset=2
    )
    assert total2 == 5
    assert len(page2) == 2

    # Page 3 (limit 2, offset 4)
    page3, total3 = await repository.list_by_assessment(
        "assessment-100", tenant_id="tenant-100", limit=2, offset=4
    )
    assert total3 == 5
    assert len(page3) == 1

    # Isolation check: other tenant only sees 1 result
    other_page, other_total = await repository.list_by_assessment(
        "assessment-100", tenant_id="tenant-200", limit=10, offset=0
    )
    assert other_total == 1
    assert len(other_page) == 1
    assert other_page[0].attempt_id == "attempt-other"

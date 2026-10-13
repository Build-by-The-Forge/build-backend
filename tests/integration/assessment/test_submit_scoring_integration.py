from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.assessment.attempt_service import AttemptService
from app.domain.assessment.assessment import Assessment
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.assessment.errors import AttemptAlreadySubmittedError
from app.domain.assessment.question import Question, QuestionOption
from app.domain.assessment.value_objects import (
    QuestionDisplayOrder,
    QuestionMarks,
    QuestionOptionId,
    QuestionOptionText,
    QuestionPrompt,
    QuestionType,
)
from app.events.base import DomainEvent
from app.events.event_bus import EventBus
from app.infrastructure.assessment.repositories import (
    SqlAlchemyAssessmentRepository,
    SqlAlchemyAttemptAnswerRepository,
    SqlAlchemyAttemptRepository,
    SqlAlchemyAttemptResultRepository,
    SqlAlchemyQuestionRepository,
)
from app.infrastructure.assessment.unit_of_work import (
    AssessmentUnitOfWork,
    assessment_unit_of_work,
)


@pytest.mark.asyncio
async def test_submit_attempt_calculates_and_persists_result_with_events(
    session: AsyncSession,
) -> None:
    # 1. Setup Question in QuestionBank
    question_repo = SqlAlchemyQuestionRepository(session)
    q1 = Question.create(
        tenant_id="tenant-123",
        topic_id="topic-1",
        question_type=QuestionType.MCQ,
        prompt=QuestionPrompt("What is 10 + 10?"),
        marks=QuestionMarks(5),
        options=[
            QuestionOption(
                id=QuestionOptionId("opt-1"),
                question_id=None,  # type: ignore[arg-type]
                text=QuestionOptionText("15"),
                display_order=QuestionDisplayOrder(1),
                is_correct=False,
            ),
            QuestionOption(
                id=QuestionOptionId("opt-2"),
                question_id=None,  # type: ignore[arg-type]
                text=QuestionOptionText("20"),
                display_order=QuestionDisplayOrder(2),
                is_correct=True,
            ),
        ],
    )
    await question_repo.save(q1, tenant_id="tenant-123")

    # 2. Setup Assessment with snapshot
    assessment_repo = SqlAlchemyAssessmentRepository(session)
    assessment = Assessment.create(
        tenant_id="tenant-123",
        course_id="course-123",
        title="Math Test",
        instructions="Complete exam",
        duration_minutes=30,
        passing_score=5,
    )
    correct_idx = next((i for i, opt in enumerate(q1.options) if opt.is_correct), 0)
    assessment.add_question(
        question_id=q1.id.value,
        prompt=q1.prompt.value,
        options=[opt.text.value for opt in q1.options],
        marks=int(q1.marks.value),
        correct_option_index=correct_idx,
    )
    assessment.publish()
    await assessment_repo.save(assessment, tenant_id="tenant-123")

    # 3. Start attempt
    attempt_repo = SqlAlchemyAttemptRepository(session)
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id=assessment.id,
        user_id="user-123",
    )
    await attempt_repo.save(attempt, tenant_id="tenant-123")

    # 4. Save learner answer (correct option index 1)
    snapshots = await assessment_repo.list_question_snapshots(assessment.id, tenant_id="tenant-123")
    answer_repo = SqlAlchemyAttemptAnswerRepository(session)
    answer = AttemptAnswer.create(
        tenant_id="tenant-123",
        attempt_id=attempt.id,
        assessment_question_id=snapshots[0].assessment_question_id or snapshots[0].question_id,
        selected_option_index=1,
    )
    await answer_repo.save(answer)

    # 5. Service setup with UoW and EventBus
    event_bus = EventBus()
    emitted_events: list[DomainEvent] = []
    event_bus.subscribe("attempt.submitted", lambda e: emitted_events.append(e))
    event_bus.subscribe("attempt.graded", lambda e: emitted_events.append(e))

    @asynccontextmanager
    async def uow_factory() -> AsyncIterator[AssessmentUnitOfWork]:
        async with assessment_unit_of_work(session) as uow:
            yield uow

    service = AttemptService(event_bus=event_bus, uow_factory=uow_factory)

    # 6. Submit attempt
    submitted_attempt = await service.submit_attempt(attempt.id, "tenant-123", "user-123")
    assert submitted_attempt is not None
    assert submitted_attempt.status == AttemptStatus.SUBMITTED
    assert submitted_attempt.submitted_at is not None

    # 7. Check AttemptResult persisted
    result_repo = SqlAlchemyAttemptResultRepository(session)
    result = await result_repo.get_by_attempt_id(attempt.id, tenant_id="tenant-123")
    assert result is not None
    assert result.total_score == 5
    assert result.max_score == 5
    assert result.percentage == 100.0
    assert result.passed is True
    assert len(result.breakdown) == 1
    assert result.breakdown[0].is_correct is True
    assert result.breakdown[0].awarded_marks == 5

    # 8. Check events
    assert len(emitted_events) == 2
    assert emitted_events[0].event_type == "attempt.submitted"
    assert emitted_events[1].event_type == "attempt.graded"
    assert emitted_events[1].payload["total_score"] == 5

    # 9. Test double submit raises error
    with pytest.raises(AttemptAlreadySubmittedError):
        await service.submit_attempt(attempt.id, "tenant-123", "user-123")

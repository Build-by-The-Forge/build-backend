import pytest
from app.domain.assessment.result import AttemptResult, QuestionResult


def test_question_result_creation_and_validation() -> None:
    qr = QuestionResult(
        assessment_question_id="aq-1",
        selected_option_index=1,
        correct_option_index=1,
        awarded_marks=2,
        max_marks=2,
        is_correct=True,
    )
    assert qr.assessment_question_id == "aq-1"
    assert qr.selected_option_index == 1
    assert qr.correct_option_index == 1
    assert qr.awarded_marks == 2
    assert qr.max_marks == 2
    assert qr.is_correct is True

    # Unanswered case
    unanswered_qr = QuestionResult(
        assessment_question_id="aq-2",
        selected_option_index=None,
        correct_option_index=0,
        awarded_marks=0,
        max_marks=1,
        is_correct=False,
    )
    assert unanswered_qr.selected_option_index is None
    assert unanswered_qr.is_correct is False

    with pytest.raises(ValueError, match="assessment_question_id is required"):
        QuestionResult(
            assessment_question_id="",
            selected_option_index=0,
            correct_option_index=0,
            awarded_marks=1,
            max_marks=1,
            is_correct=True,
        )

    with pytest.raises(ValueError, match="correct_option_index must be non-negative"):
        QuestionResult(
            assessment_question_id="aq-1",
            selected_option_index=0,
            correct_option_index=-1,
            awarded_marks=0,
            max_marks=1,
            is_correct=False,
        )

    with pytest.raises(ValueError, match="max_marks must be positive"):
        QuestionResult(
            assessment_question_id="aq-1",
            selected_option_index=0,
            correct_option_index=0,
            awarded_marks=0,
            max_marks=0,
            is_correct=False,
        )

    with pytest.raises(ValueError, match="awarded_marks must be between 0 and max_marks"):
        QuestionResult(
            assessment_question_id="aq-1",
            selected_option_index=0,
            correct_option_index=0,
            awarded_marks=5,
            max_marks=2,
            is_correct=True,
        )


def test_attempt_result_creation_and_events() -> None:
    qr = QuestionResult(
        assessment_question_id="aq-1",
        selected_option_index=0,
        correct_option_index=0,
        awarded_marks=5,
        max_marks=5,
        is_correct=True,
    )
    result = AttemptResult.create(
        tenant_id="tenant-1",
        attempt_id="attempt-1",
        assessment_id="assessment-1",
        user_id="user-1",
        total_score=5,
        max_score=5,
        percentage=100.0,
        passed=True,
        breakdown=[qr],
    )

    assert result.tenant_id == "tenant-1"
    assert result.attempt_id == "attempt-1"
    assert result.assessment_id == "assessment-1"
    assert result.user_id == "user-1"
    assert result.total_score == 5
    assert result.max_score == 5
    assert result.percentage == 100.0
    assert result.passed is True
    assert len(result.breakdown) == 1
    assert result.id.startswith("result-")

    events = result.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "attempt.graded"
    assert events[0].payload["attempt_id"] == "attempt-1"
    assert events[0].payload["passed"] is True
    assert events[0].payload["percentage"] == 100.0


def test_attempt_result_validation() -> None:
    with pytest.raises(ValueError, match="tenant_id is required"):
        AttemptResult.create(
            tenant_id="",
            attempt_id="attempt-1",
            assessment_id="assessment-1",
            user_id="user-1",
            total_score=0,
            max_score=10,
            percentage=0.0,
            passed=False,
        )

    with pytest.raises(ValueError, match="total_score cannot exceed max_score"):
        AttemptResult.create(
            tenant_id="tenant-1",
            attempt_id="attempt-1",
            assessment_id="assessment-1",
            user_id="user-1",
            total_score=15,
            max_score=10,
            percentage=100.0,
            passed=True,
        )

from datetime import datetime

import pytest

from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.assessment.errors import AttemptAlreadySubmittedError


def test_attempt_answer_validates_option_index() -> None:
    answer = AttemptAnswer.create(
        tenant_id="tenant-123",
        attempt_id="attempt-123",
        assessment_question_id="assessment-question-123",
        selected_option_index=1,
    )

    assert answer.selected_option_index == 1
    assert answer.tenant_id == "tenant-123"
    assert answer.attempt_id == "attempt-123"
    assert answer.assessment_question_id == "assessment-question-123"
    assert isinstance(answer.created_at, datetime)
    assert isinstance(answer.updated_at, datetime)

    answer.update_selection(2, option_count=4)
    assert answer.selected_option_index == 2

    with pytest.raises(ValueError, match="selected_option_index"):
        answer.update_selection(4, option_count=4)


def test_attempt_answer_tracks_last_update_time_when_selection_changes() -> None:
    answer = AttemptAnswer.create(
        tenant_id="tenant-123",
        attempt_id="attempt-456",
        assessment_question_id="assessment-question-456",
        selected_option_index=0,
    )

    original_updated_at = answer.updated_at
    answer.update_selection(3, option_count=4)

    assert answer.updated_at >= original_updated_at
    assert answer.selected_option_index == 3


def test_attempt_prevents_answer_mutation_after_submission() -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )
    attempt.submit()

    with pytest.raises(AttemptAlreadySubmittedError, match="already submitted"):
        attempt.ensure_answer_mutation_allowed()

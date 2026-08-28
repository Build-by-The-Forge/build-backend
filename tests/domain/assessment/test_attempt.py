from datetime import datetime

import pytest
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.errors import AttemptAlreadySubmittedError


def test_attempt_starts_in_progress_with_owner_metadata() -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )

    assert attempt.status == AttemptStatus.IN_PROGRESS
    assert attempt.tenant_id == "tenant-123"
    assert attempt.assessment_id == "assessment-123"
    assert attempt.user_id == "user-123"
    assert attempt.started_at is not None
    assert attempt.submitted_at is None

    events = attempt.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "attempt.started"
    assert events[0].payload == {
        "attempt_id": attempt.id,
        "assessment_id": "assessment-123",
        "tenant_id": "tenant-123",
        "user_id": "user-123",
    }


def test_attempt_submission_sets_timestamp_and_emits_event() -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )
    attempt.pull_events()

    attempt.submit()

    assert attempt.status == AttemptStatus.SUBMITTED
    assert isinstance(attempt.submitted_at, datetime)
    assert attempt.updated_at == attempt.submitted_at
    events = attempt.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "attempt.submitted"


def test_submitted_attempt_cannot_be_submitted_again() -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
    )
    attempt.submit()

    with pytest.raises(AttemptAlreadySubmittedError, match="already submitted"):
        attempt.submit()


def test_submitted_attempt_requires_submitted_timestamp() -> None:
    with pytest.raises(ValueError, match="submitted_at is required"):
        AssessmentAttempt(
            tenant_id="tenant-123",
            assessment_id="assessment-123",
            user_id="user-123",
            status=AttemptStatus.SUBMITTED,
        )

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.errors import AttemptAlreadySubmittedError, AttemptExpiredError


def test_attempt_starts_in_progress_with_owner_metadata() -> None:
    attempt = AssessmentAttempt.start(
        tenant_id="tenant-123",
        assessment_id="assessment-123",
        user_id="user-123",
        duration_minutes=30,
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
        duration_minutes=30,
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
        duration_minutes=30,
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
            expires_at=datetime.now(timezone.utc),
            status=AttemptStatus.SUBMITTED,
        )


def _attempt() -> AssessmentAttempt:
    return AssessmentAttempt.start(tenant_id="t", assessment_id="a", user_id="u", duration_minutes=30)


def test_the_deadline_comes_from_the_start_time_and_duration() -> None:
    attempt = _attempt()
    assert attempt.expires_at == attempt.started_at + timedelta(minutes=30)


def test_the_last_instant_before_the_deadline_is_in_time() -> None:
    attempt = _attempt()
    just_before = attempt.expires_at - timedelta(microseconds=1)
    assert attempt.is_expired(just_before) is False
    attempt.ensure_answer_mutation_allowed(just_before)


def test_the_exact_deadline_is_late() -> None:
    attempt = _attempt()
    assert attempt.is_expired(attempt.expires_at) is True
    with pytest.raises(AttemptExpiredError):
        attempt.ensure_answer_mutation_allowed(attempt.expires_at)


def test_a_stored_naive_deadline_is_read_as_utc() -> None:
    attempt = _attempt()
    attempt.expires_at = attempt.expires_at.replace(tzinfo=None)
    assert attempt.is_expired(attempt.started_at) is False
    assert attempt.is_expired(attempt.started_at + timedelta(minutes=30)) is True


def test_a_submitted_attempt_reports_that_first_even_after_the_deadline() -> None:
    attempt = _attempt()
    attempt.submit()
    with pytest.raises(AttemptAlreadySubmittedError):
        attempt.ensure_answer_mutation_allowed(attempt.expires_at + timedelta(days=1))

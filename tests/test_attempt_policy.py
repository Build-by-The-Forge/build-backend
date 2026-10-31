"""AttemptPolicy: the combinations that can exist, and when another attempt may start."""

from dataclasses import replace
from itertools import product

import pytest

from app.domain.assessment.assessment import Assessment, AssessmentStatus
from app.domain.assessment.attempt_policy import (
    AttemptKind,
    AttemptPolicy,
    FeedbackTiming,
    ResultVisibility,
    ScoringPolicy,
)
from app.domain.assessment.errors import AttemptPolicyLockedError

DEFAULT = AttemptPolicy.practice_default()


def build(max_attempts, retake, feedback=FeedbackTiming.IMMEDIATE):
    return AttemptPolicy(
        kind=AttemptKind.FORMAL,
        max_attempts=max_attempts,
        retake_after_submission=retake,
        result_visibility=ResultVisibility.IMMEDIATE,
        feedback_timing=feedback,
        scoring_policy=ScoringPolicy.BEST,
    )


def draft():
    return Assessment(tenant_id="t", course_id="c", title="T", instructions="I", duration_minutes=30)


def test_the_default_matches_todays_behaviour():
    assert DEFAULT.kind is AttemptKind.PRACTICE
    assert DEFAULT.max_attempts is None
    assert DEFAULT.retake_after_submission is True
    assert DEFAULT.result_visibility is ResultVisibility.IMMEDIATE
    assert DEFAULT.feedback_timing is FeedbackTiming.IMMEDIATE
    assert DEFAULT.scoring_policy is ScoringPolicy.BEST


@pytest.mark.parametrize("max_attempts,retake", [(None, True), (2, True), (5, True), (1, False)])
def test_valid_limits_and_retakes(max_attempts, retake):
    assert build(max_attempts, retake).max_attempts == max_attempts


@pytest.mark.parametrize("max_attempts,retake", [(1, True), (None, False), (2, False), (0, True), (0, False), (-1, True)])
def test_contradictory_limits_and_retakes_cannot_exist(max_attempts, retake):
    with pytest.raises(ValueError):
        build(max_attempts, retake)


def test_feedback_after_the_final_attempt_needs_a_limit():
    with pytest.raises(ValueError):
        build(None, True, FeedbackTiming.AFTER_FINAL_ATTEMPT)
    assert build(3, True, FeedbackTiming.AFTER_FINAL_ATTEMPT).max_attempts == 3


def test_every_combination_of_the_independent_settings_is_valid():
    for kind, visibility, feedback, scoring in product(AttemptKind, ResultVisibility, FeedbackTiming, ScoringPolicy):
        assert replace(build(2, True), kind=kind, result_visibility=visibility, feedback_timing=feedback, scoring_policy=scoring)


@pytest.mark.parametrize(
    "max_attempts,retake,used,allowed",
    [
        (1, False, 0, True),
        (1, False, 1, False),
        (3, True, 2, True),
        (3, True, 3, False),
        (3, True, 4, False),
        (None, True, 1000, True),
    ],
)
def test_every_started_attempt_counts_toward_the_limit(max_attempts, retake, used, allowed):
    assert build(max_attempts, retake).allows_new_attempt(used) is allowed


def test_a_draft_can_change_its_policy():
    assessment = draft()
    assessment.update_details(attempt_policy=build(1, False))
    assert assessment.attempt_policy.max_attempts == 1


@pytest.mark.parametrize("status", [AssessmentStatus.PUBLISHED, AssessmentStatus.OPEN, AssessmentStatus.CLOSED])
def test_the_policy_locks_at_publication_and_a_refusal_changes_nothing(status):
    assessment = draft()
    assessment.status = status
    with pytest.raises(AttemptPolicyLockedError):
        assessment.update_details(title="Changed", attempt_policy=build(1, False))
    assert assessment.attempt_policy == DEFAULT
    assert assessment.title == "T"


def test_other_details_can_still_change_after_publication():
    assessment = draft()
    assessment.status = AssessmentStatus.PUBLISHED
    assessment.update_details(title="Changed")
    assert assessment.title == "Changed"

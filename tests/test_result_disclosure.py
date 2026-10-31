"""The precedence of result visibility and feedback timing, and which attempt stands."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.assessment.attempt_policy import AttemptPolicy, FeedbackTiming, ResultVisibility, ScoringPolicy
from app.domain.assessment.result_disclosure import AttemptOutcome, disclose, standing_attempts

BASE = replace(AttemptPolicy.practice_default(), max_attempts=2)
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
IMMEDIATE, AFTER_RELEASE = ResultVisibility.IMMEDIATE, ResultVisibility.AFTER_RELEASE


def decide(visibility, timing, *, finalized=True, released=False, used=1, all_finalized=True):
    policy = replace(BASE, result_visibility=visibility, feedback_timing=timing)
    return disclose(policy, finalized=finalized, released=released, attempts_used=used, all_finalized=all_finalized)


# (visibility, timing, released, used, all finalized) -> (result visible, feedback shown)
PRECEDENCE = [
    (IMMEDIATE, FeedbackTiming.IMMEDIATE, False, 1, True, True, True),
    (IMMEDIATE, FeedbackTiming.NEVER, False, 1, True, True, False),
    (IMMEDIATE, FeedbackTiming.NEVER, True, 2, True, True, False),
    (IMMEDIATE, FeedbackTiming.AFTER_RELEASE, False, 1, True, True, False),
    (IMMEDIATE, FeedbackTiming.AFTER_RELEASE, True, 1, True, True, True),
    (IMMEDIATE, FeedbackTiming.AFTER_FINAL_ATTEMPT, False, 1, True, True, False),
    (IMMEDIATE, FeedbackTiming.AFTER_FINAL_ATTEMPT, False, 2, False, True, False),
    (IMMEDIATE, FeedbackTiming.AFTER_FINAL_ATTEMPT, False, 2, True, True, True),
    (AFTER_RELEASE, FeedbackTiming.IMMEDIATE, False, 1, True, False, False),
    (AFTER_RELEASE, FeedbackTiming.IMMEDIATE, True, 1, True, True, True),
    (AFTER_RELEASE, FeedbackTiming.NEVER, False, 2, True, False, False),
    (AFTER_RELEASE, FeedbackTiming.NEVER, True, 2, True, True, False),
    (AFTER_RELEASE, FeedbackTiming.AFTER_RELEASE, False, 1, True, False, False),
    (AFTER_RELEASE, FeedbackTiming.AFTER_RELEASE, True, 1, True, True, True),
    # The final attempt reached doesn't override an unreleased result.
    (AFTER_RELEASE, FeedbackTiming.AFTER_FINAL_ATTEMPT, False, 2, True, False, False),
    (AFTER_RELEASE, FeedbackTiming.AFTER_FINAL_ATTEMPT, True, 1, True, True, False),
    (AFTER_RELEASE, FeedbackTiming.AFTER_FINAL_ATTEMPT, True, 2, True, True, True),
]


@pytest.mark.parametrize("visibility,timing,released,used,all_finalized,visible,shown", PRECEDENCE)
def test_precedence(visibility, timing, released, used, all_finalized, visible, shown):
    outcome = decide(visibility, timing, released=released, used=used, all_finalized=all_finalized)
    assert (outcome.result_visible, outcome.feedback_shown) == (visible, shown)


@pytest.mark.parametrize("visibility", list(ResultVisibility))
@pytest.mark.parametrize("timing", list(FeedbackTiming))
def test_nothing_is_visible_before_finalization(visibility, timing):
    outcome = decide(visibility, timing, finalized=False, released=True, used=2)
    assert (outcome.result_visible, outcome.feedback_shown) == (False, False)


@pytest.mark.parametrize("visibility", list(ResultVisibility))
@pytest.mark.parametrize("timing", list(FeedbackTiming))
@pytest.mark.parametrize("released", [False, True])
def test_feedback_never_shows_without_the_result(visibility, timing, released):
    outcome = decide(visibility, timing, released=released, used=2)
    assert outcome.result_visible or not outcome.feedback_shown


def outcome(attempt_id, score, started=0, finalized=10, user="u1"):
    return AttemptOutcome(attempt_id, user, score, T0 + timedelta(hours=started), T0 + timedelta(hours=finalized))


def test_best_is_the_highest_score():
    outcomes = [outcome("a", 3), outcome("b", 9, finalized=20), outcome("c", 5)]
    assert standing_attempts(ScoringPolicy.BEST, outcomes) == {"b"}


def test_best_breaks_a_tie_by_the_earliest_finalized_then_the_id():
    assert standing_attempts(ScoringPolicy.BEST, [outcome("a", 5, finalized=20), outcome("b", 5, finalized=10)]) == {"b"}
    assert standing_attempts(ScoringPolicy.BEST, [outcome("b", 5), outcome("a", 5)]) == {"a"}


def test_latest_is_the_latest_finalized_whatever_its_score():
    outcomes = [outcome("a", 9, finalized=10), outcome("b", 1, finalized=20)]
    assert standing_attempts(ScoringPolicy.LATEST, outcomes) == {"b"}
    assert standing_attempts(ScoringPolicy.LATEST, [outcome("b", 1), outcome("a", 1)]) == {"a"}


def test_first_is_the_earliest_started_even_if_finalized_later():
    outcomes = [outcome("a", 1, started=0, finalized=30), outcome("b", 9, started=5, finalized=6)]
    assert standing_attempts(ScoringPolicy.FIRST, outcomes) == {"a"}
    assert standing_attempts(ScoringPolicy.FIRST, [outcome("b", 1), outcome("a", 1)]) == {"a"}


@pytest.mark.parametrize("scoring", list(ScoringPolicy))
def test_one_attempt_stands_per_student_in_any_order(scoring):
    outcomes = [outcome("a", 1), outcome("b", 2, finalized=11), outcome("c", 7, user="u2"), outcome("d", 3, user="u2")]
    assert len(standing_attempts(scoring, outcomes)) == 2
    assert standing_attempts(scoring, outcomes) == standing_attempts(scoring, reversed(outcomes))

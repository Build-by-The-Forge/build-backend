"""What a student may see of a result, and which attempt stands
(docs/assessment-lifecycle-plan.md, L2). Pure functions: no database access.

A score can reveal withheld feedback, most plainly on a one-question assessment.
Feedback timing limits what is shown; it doesn't guarantee concealment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.domain.assessment.attempt_policy import AttemptPolicy, FeedbackTiming, ResultVisibility, ScoringPolicy


@dataclass(frozen=True, slots=True)
class ResultDisclosure:
    result_visible: bool
    feedback_shown: bool


def disclose(
    policy: AttemptPolicy,
    *,
    finalized: bool,
    released: bool,
    attempts_used: int,
    all_finalized: bool,
) -> ResultDisclosure:
    """Neither setting overrides the other: feedback needs both to permit it."""
    result_visible = finalized and (policy.result_visibility is ResultVisibility.IMMEDIATE or released)
    return ResultDisclosure(
        result_visible=result_visible,
        feedback_shown=result_visible and _feedback_reached(policy, released, attempts_used, all_finalized),
    )


def _feedback_reached(policy: AttemptPolicy, released: bool, attempts_used: int, all_finalized: bool) -> bool:
    match policy.feedback_timing:
        case FeedbackTiming.IMMEDIATE:
            return True
        case FeedbackTiming.AFTER_FINAL_ATTEMPT:
            return attempts_used == policy.max_attempts and all_finalized
        case FeedbackTiming.AFTER_RELEASE:
            return released
        case FeedbackTiming.NEVER:
            return False


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    attempt_id: str
    user_id: str
    total_score: int
    started_at: datetime
    finalized_at: datetime


def _stands_key(scoring: ScoringPolicy, outcome: AttemptOutcome) -> tuple:
    """The smallest key stands. Each ends in the attempt's ID, so the choice is deterministic."""
    match scoring:
        case ScoringPolicy.BEST:
            return (-outcome.total_score, outcome.finalized_at, outcome.attempt_id)
        case ScoringPolicy.LATEST:
            # Negated, so the latest finalized sorts first.
            return (-outcome.finalized_at.timestamp(), outcome.attempt_id)
        case ScoringPolicy.FIRST:
            return (outcome.started_at, outcome.attempt_id)


def standing_attempts(scoring: ScoringPolicy, outcomes: Iterable[AttemptOutcome]) -> set[str]:
    """The attempt that stands for each student. Each attempt's own result is unchanged."""
    standing: dict[str, AttemptOutcome] = {}
    for outcome in outcomes:
        current = standing.get(outcome.user_id)
        if current is None or _stands_key(scoring, outcome) < _stands_key(scoring, current):
            standing[outcome.user_id] = outcome
    return {outcome.attempt_id for outcome in standing.values()}

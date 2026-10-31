"""How an assessment's attempts work (docs/assessment-lifecycle-plan.md, L1).

Fixed at publication, so nobody's attempts are judged by rules changed midway.
Combinations outside these rules can't be built, and CHECK constraints refuse
them in the database too.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AttemptKind(StrEnum):
    PRACTICE = "practice"
    FORMAL = "formal"


class ResultVisibility(StrEnum):
    IMMEDIATE = "immediate"
    AFTER_RELEASE = "after_release"


class FeedbackTiming(StrEnum):
    IMMEDIATE = "immediate"
    AFTER_FINAL_ATTEMPT = "after_final_attempt"
    AFTER_RELEASE = "after_release"
    NEVER = "never"


class ScoringPolicy(StrEnum):
    BEST = "best"
    LATEST = "latest"
    FIRST = "first"


@dataclass(frozen=True, slots=True)
class AttemptPolicy:
    kind: AttemptKind
    max_attempts: int | None
    retake_after_submission: bool
    result_visibility: ResultVisibility
    feedback_timing: FeedbackTiming
    scoring_policy: ScoringPolicy

    def __post_init__(self) -> None:
        if self.max_attempts is not None and self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retake_after_submission == (self.max_attempts == 1):
            raise ValueError("a retake needs max_attempts null or above 1, and no retake needs exactly 1")
        if self.feedback_timing is FeedbackTiming.AFTER_FINAL_ATTEMPT and self.max_attempts is None:
            raise ValueError("after_final_attempt needs a limit, since it's never reached without one")

    @classmethod
    def practice_default(cls) -> AttemptPolicy:
        """Today's behaviour, for assessments that don't choose a policy."""
        return cls(
            kind=AttemptKind.PRACTICE,
            max_attempts=None,
            retake_after_submission=True,
            result_visibility=ResultVisibility.IMMEDIATE,
            feedback_timing=FeedbackTiming.IMMEDIATE,
            scoring_policy=ScoringPolicy.BEST,
        )

    def allows_new_attempt(self, attempts_used: int) -> bool:
        """Every started attempt counts, however it ended."""
        return self.max_attempts is None or attempts_used < self.max_attempts

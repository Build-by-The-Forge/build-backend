from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.events.base import DomainEvent


@dataclass(slots=True)
class QuestionResult:
    assessment_question_id: str
    selected_option_index: int | None
    correct_option_index: int
    awarded_marks: int
    max_marks: int
    is_correct: bool

    def __post_init__(self) -> None:
        if not self.assessment_question_id.strip():
            raise ValueError("assessment_question_id is required")
        if self.correct_option_index < 0:
            raise ValueError("correct_option_index must be non-negative")
        if self.selected_option_index is not None and self.selected_option_index < 0:
            raise ValueError("selected_option_index must be non-negative if provided")
        if self.max_marks <= 0:
            raise ValueError("max_marks must be positive")
        if self.awarded_marks < 0 or self.awarded_marks > self.max_marks:
            raise ValueError("awarded_marks must be between 0 and max_marks")


@dataclass(slots=True)
class AttemptResult:
    tenant_id: str
    attempt_id: str
    assessment_id: str
    user_id: str
    total_score: int
    max_score: int
    percentage: float
    passed: bool
    breakdown: list[QuestionResult] = field(default_factory=list)
    result_id: str = field(default_factory=lambda: f"result-{uuid4()}", repr=False)
    graded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.attempt_id.strip():
            raise ValueError("attempt_id is required")
        if not self.assessment_id.strip():
            raise ValueError("assessment_id is required")
        if not self.user_id.strip():
            raise ValueError("user_id is required")
        if self.total_score < 0:
            raise ValueError("total_score cannot be negative")
        if self.max_score < 0:
            raise ValueError("max_score cannot be negative")
        if self.total_score > self.max_score:
            raise ValueError("total_score cannot exceed max_score")
        if self.percentage < 0.0 or self.percentage > 100.0:
            raise ValueError("percentage must be between 0.0 and 100.0")

    @property
    def id(self) -> str:
        return self.result_id

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        attempt_id: str,
        assessment_id: str,
        user_id: str,
        total_score: int,
        max_score: int,
        percentage: float,
        passed: bool,
        breakdown: list[QuestionResult] | None = None,
        result_id: str | None = None,
        graded_at: datetime | None = None,
    ) -> "AttemptResult":
        result = cls(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            assessment_id=assessment_id,
            user_id=user_id,
            total_score=total_score,
            max_score=max_score,
            percentage=percentage,
            passed=passed,
            breakdown=list(breakdown or []),
            result_id=result_id or f"result-{uuid4()}",
            graded_at=graded_at or datetime.now(timezone.utc),
        )
        result._events.append(
            DomainEvent(
                event_type="attempt.graded",
                payload={
                    "result_id": result.id,
                    "attempt_id": result.attempt_id,
                    "assessment_id": result.assessment_id,
                    "tenant_id": result.tenant_id,
                    "user_id": result.user_id,
                    "total_score": result.total_score,
                    "max_score": result.max_score,
                    "percentage": result.percentage,
                    "passed": result.passed,
                },
            )
        )
        return result

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import uuid4

from app.domain.assessment.errors import AttemptAlreadySubmittedError, AttemptExpiredError
from app.events.base import DomainEvent


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; every stored value is UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"


class FinalizedBy(StrEnum):
    STUDENT = "student"
    DEADLINE = "deadline"


@dataclass(slots=True)
class AssessmentAttempt:
    tenant_id: str
    assessment_id: str
    user_id: str
    # Fixed when the attempt starts, so editing the assessment can't move it.
    expires_at: datetime
    status: AttemptStatus = AttemptStatus.IN_PROGRESS
    attempt_id: str = field(default_factory=lambda: f"attempt-{uuid4()}", repr=False)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: datetime | None = None
    finalized_by: FinalizedBy | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # True only on the call that submitted it, not on a repeat. Not stored.
    newly_submitted: bool = field(default=False, repr=False)
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.assessment_id.strip():
            raise ValueError("assessment_id is required")
        if not self.user_id.strip():
            raise ValueError("user_id is required")
        if self.status == AttemptStatus.SUBMITTED and self.submitted_at is None:
            raise ValueError("submitted_at is required for submitted attempts")

    @classmethod
    def start(
        cls,
        *,
        tenant_id: str,
        assessment_id: str,
        user_id: str,
        duration_minutes: int,
        now: datetime | None = None,
    ) -> AssessmentAttempt:
        started_at = now or datetime.now(timezone.utc)
        attempt = cls(
            tenant_id=tenant_id,
            assessment_id=assessment_id,
            user_id=user_id,
            started_at=started_at,
            expires_at=started_at + timedelta(minutes=duration_minutes),
        )
        attempt._events.append(
            DomainEvent(
                event_type="attempt.started",
                payload={
                    "attempt_id": attempt.id,
                    "assessment_id": attempt.assessment_id,
                    "tenant_id": attempt.tenant_id,
                    "user_id": attempt.user_id,
                },
            )
        )
        return attempt

    @property
    def id(self) -> str:
        return self.attempt_id

    def submit(self, now: datetime | None = None, finalized_by: FinalizedBy = FinalizedBy.STUDENT) -> None:
        if self.status == AttemptStatus.SUBMITTED:
            raise AttemptAlreadySubmittedError("attempt already submitted")
        self.status = AttemptStatus.SUBMITTED
        self.newly_submitted = True
        self.submitted_at = now or datetime.now(timezone.utc)
        self.finalized_by = finalized_by
        self.updated_at = self.submitted_at
        self._events.append(
            DomainEvent(
                event_type="attempt.submitted",
                payload={
                    "attempt_id": self.id,
                    "assessment_id": self.assessment_id,
                    "tenant_id": self.tenant_id,
                    "user_id": self.user_id,
                },
            )
        )

    def is_expired(self, now: datetime) -> bool:
        """Expired from the deadline itself onwards: the exact instant is late.
        The time is required, so one clock decides: the database's, read after
        the row lock (AttemptRepository.database_now)."""
        return _as_utc(now) >= _as_utc(self.expires_at)

    def ensure_answer_mutation_allowed(self, now: datetime) -> None:
        if self.status == AttemptStatus.SUBMITTED:
            raise AttemptAlreadySubmittedError("attempt already submitted")
        if self.is_expired(now):
            raise AttemptExpiredError("attempt expired")

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

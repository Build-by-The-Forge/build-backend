from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from app.domain.assessment.errors import AttemptAlreadySubmittedError
from app.events.base import DomainEvent


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"


@dataclass(slots=True)
class AssessmentAttempt:
    tenant_id: str
    assessment_id: str
    user_id: str
    status: AttemptStatus = AttemptStatus.IN_PROGRESS
    attempt_id: str = field(default_factory=lambda: f"attempt-{uuid4()}", repr=False)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
    ) -> AssessmentAttempt:
        attempt = cls(
            tenant_id=tenant_id,
            assessment_id=assessment_id,
            user_id=user_id,
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

    def submit(self) -> None:
        if self.status == AttemptStatus.SUBMITTED:
            raise AttemptAlreadySubmittedError("attempt already submitted")
        self.status = AttemptStatus.SUBMITTED
        self.submitted_at = datetime.now(timezone.utc)
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

    def ensure_answer_mutation_allowed(self) -> None:
        if self.status == AttemptStatus.SUBMITTED:
            raise AttemptAlreadySubmittedError("attempt already submitted")

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

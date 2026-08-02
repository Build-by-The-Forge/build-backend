from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.value_objects import (
    CourseId,
    LearningOutcomeDescription,
    LearningOutcomeId,
    LearningOutcomeSequence,
    LearningOutcomeStatus,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class LearningOutcome:
    id: LearningOutcomeId
    course_id: CourseId
    sequence: LearningOutcomeSequence
    description: LearningOutcomeDescription
    status: LearningOutcomeStatus = LearningOutcomeStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        course_id: CourseId,
        sequence: LearningOutcomeSequence,
        description: LearningOutcomeDescription,
        learning_outcome_id: LearningOutcomeId | None = None,
    ) -> LearningOutcome:
        lo = cls(
            id=learning_outcome_id or LearningOutcomeId(""),
            course_id=course_id,
            sequence=sequence,
            description=description,
            status=LearningOutcomeStatus.ACTIVE,
        )
        lo._events.append(
            DomainEvent(
                event_type="learning_outcome.created",
                payload={
                    "learning_outcome_id": lo.id.value,
                    "course_id": lo.course_id.value,
                },
            )
        )
        return lo

    def archive(self) -> None:
        self.status = LearningOutcomeStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="learning_outcome.archived",
                payload={"learning_outcome_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

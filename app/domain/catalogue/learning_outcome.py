from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.errors import LearningOutcomeAlreadyArchivedError
from app.domain.catalogue.value_objects import (
    LearningOutcomeDescription,
    LearningOutcomeId,
    LearningOutcomeSequence,
    LearningOutcomeStatus,
    TopicId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class LearningOutcome:
    id: LearningOutcomeId
    topic_id: TopicId
    sequence: LearningOutcomeSequence
    description: LearningOutcomeDescription
    status: LearningOutcomeStatus = LearningOutcomeStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        topic_id: TopicId,
        sequence: LearningOutcomeSequence,
        description: LearningOutcomeDescription,
        learning_outcome_id: LearningOutcomeId | None = None,
    ) -> LearningOutcome:
        lo = cls(
            id=learning_outcome_id or LearningOutcomeId(""),
            topic_id=topic_id,
            sequence=sequence,
            description=description,
            status=LearningOutcomeStatus.ACTIVE,
        )
        lo._events.append(
            DomainEvent(
                event_type="learning_outcome.created",
                payload={
                    "learning_outcome_id": lo.id.value,
                    "topic_id": lo.topic_id.value,
                },
            )
        )
        return lo

    def archive(self) -> None:
        if self.status == LearningOutcomeStatus.ARCHIVED:
            raise LearningOutcomeAlreadyArchivedError(
                "learning outcome already archived"
            )
        self.status = LearningOutcomeStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="learning_outcome.archived",
                payload={"learning_outcome_id": self.id.value},
            )
        )

    def publish(self) -> None:
        if self.status == LearningOutcomeStatus.ACTIVE:
            return
        self.status = LearningOutcomeStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="learning_outcome.published",
                payload={"learning_outcome_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    @property
    def is_active(self) -> bool:
        return self.status == LearningOutcomeStatus.ACTIVE

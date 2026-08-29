from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.domain.catalogue.errors import TopicAlreadyArchivedError
from app.domain.catalogue.value_objects import (
    CourseId,
    TopicDescription,
    TopicId,
    TopicLevel,
    TopicSequence,
    TopicSlug,
    TopicStatus,
    TopicTitle,
)

if TYPE_CHECKING:
    from app.domain.catalogue.learning_outcome import LearningOutcome


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Topic:
    id: TopicId
    course_id: CourseId
    sequence: TopicSequence
    title: TopicTitle
    slug: TopicSlug
    description: TopicDescription | None = None
    level: TopicLevel = TopicLevel.PRIMARY
    status: TopicStatus = TopicStatus.ACTIVE
    learning_outcomes: list["LearningOutcome"] = field(default_factory=list, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        course_id: CourseId,
        title: TopicTitle,
        slug: TopicSlug,
        description: TopicDescription | None = None,
        level: TopicLevel = TopicLevel.PRIMARY,
        sequence: TopicSequence | None = None,
        topic_id: TopicId | None = None,
    ) -> Topic:
        topic = cls(
            id=topic_id or TopicId(""),
            course_id=course_id,
            sequence=sequence or TopicSequence(1),
            title=title,
            slug=slug,
            description=description,
            level=level,
            status=TopicStatus.ACTIVE,
        )
        topic._events.append(
            DomainEvent(
                event_type="topic.created",
                payload={
                    "topic_id": topic.id.value,
                    "course_id": topic.course_id.value,
                },
            )
        )
        return topic

    def archive(self) -> None:
        if self.status == TopicStatus.ARCHIVED:
            raise TopicAlreadyArchivedError("topic already archived")
        self.status = TopicStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="topic.archived",
                payload={"topic_id": self.id.value},
            )
        )

    def update_details(
        self, title: TopicTitle | None, description: TopicDescription | None
    ) -> None:
        changed = False
        if title is not None and title != self.title:
            self.title = title
            changed = True
        if description is not None and description != self.description:
            self.description = description
            changed = True
        if not changed:
            return
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="topic.updated",
                payload={"topic_id": self.id.value},
            )
        )

    def publish(self) -> None:
        if self.status == TopicStatus.ACTIVE:
            return
        self.status = TopicStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="topic.published",
                payload={"topic_id": self.id.value},
            )
        )

    def add_learning_outcome(self, learning_outcome: "LearningOutcome") -> None:
        if learning_outcome.topic_id != self.id:
            raise ValueError("learning outcome topic_id must match the parent topic")
        self.learning_outcomes.append(learning_outcome)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="topic.learning_outcome_added",
                payload={
                    "topic_id": self.id.value,
                    "learning_outcome_id": learning_outcome.id.value,
                },
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
        return self.status == TopicStatus.ACTIVE

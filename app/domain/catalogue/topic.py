from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.value_objects import (
    CourseId,
    TopicDescription,
    TopicId,
    TopicLevel,
    TopicSlug,
    TopicStatus,
    TopicTitle,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Topic:
    id: TopicId
    course_id: CourseId
    title: TopicTitle
    slug: TopicSlug
    description: TopicDescription | None = None
    level: TopicLevel = TopicLevel.PRIMARY
    status: TopicStatus = TopicStatus.ACTIVE
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
        topic_id: TopicId | None = None,
    ) -> Topic:
        topic = cls(
            id=topic_id or TopicId(""),
            course_id=course_id,
            title=title,
            slug=slug,
            description=description,
            level=level,
            status=TopicStatus.ACTIVE,
        )
        topic._events.append(
            DomainEvent(
                event_type="topic.created",
                payload={"topic_id": topic.id.value, "course_id": topic.course_id.value},
            )
        )
        return topic

    def archive(self) -> None:
        self.status = TopicStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="topic.archived",
                payload={"topic_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.value_objects import (
    CourseId,
    CoursePrerequisiteId,
    PrerequisiteStatus,
    PrerequisiteType,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class CoursePrerequisite:
    id: CoursePrerequisiteId
    course_id: CourseId
    prerequisite_course_id: CourseId
    prerequisite_type: PrerequisiteType = PrerequisiteType.PRE_REQUISITE
    status: PrerequisiteStatus = PrerequisiteStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        course_id: CourseId,
        prerequisite_course_id: CourseId,
        prerequisite_type: PrerequisiteType,
        prerequisite_id: CoursePrerequisiteId | None = None,
    ) -> CoursePrerequisite:
        prereq = cls(
            id=prerequisite_id or CoursePrerequisiteId(""),
            course_id=course_id,
            prerequisite_course_id=prerequisite_course_id,
            prerequisite_type=prerequisite_type,
            status=PrerequisiteStatus.ACTIVE,
        )
        prereq._events.append(
            DomainEvent(
                event_type="course_prerequisite.created",
                payload={
                    "course_id": course_id.value,
                    "prerequisite_course_id": prerequisite_course_id.value,
                },
            )
        )
        return prereq

    def archive(self) -> None:
        self.status = PrerequisiteStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course_prerequisite.archived",
                payload={"course_prerequisite_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

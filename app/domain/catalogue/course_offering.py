from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.value_objects import (
    CourseId,
    CourseOfferingId,
    CourseOfferingStatus,
    CourseOfferingType,
    SemesterNumber,
    YearLevel,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class CourseOffering:
    id: CourseOfferingId
    course_id: CourseId
    year_level: YearLevel
    semester_number: SemesterNumber
    offering_type: CourseOfferingType = CourseOfferingType.REGULAR
    status: CourseOfferingStatus = CourseOfferingStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        course_id: CourseId,
        year_level: YearLevel,
        semester_number: SemesterNumber,
        offering_type: CourseOfferingType = CourseOfferingType.REGULAR,
        course_offering_id: CourseOfferingId | None = None,
    ) -> CourseOffering:
        offering = cls(
            id=course_offering_id or CourseOfferingId(""),
            course_id=course_id,
            year_level=year_level,
            semester_number=semester_number,
            offering_type=offering_type,
            status=CourseOfferingStatus.ACTIVE,
        )
        offering._events.append(
            DomainEvent(
                event_type="course_offering.created",
                payload={
                    "course_offering_id": offering.id.value,
                    "course_id": course_id.value,
                },
            )
        )
        return offering

    def archive(self) -> None:
        self.status = CourseOfferingStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course_offering.archived",
                payload={"course_offering_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

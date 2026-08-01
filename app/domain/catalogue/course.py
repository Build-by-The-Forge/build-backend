from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseId,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseStatus,
    CourseTitle,
    DepartmentId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Course:
    id: CourseId
    department_id: DepartmentId
    code: CourseCode
    title: CourseTitle
    slug: CourseSlug
    credit_units: CourseCreditUnits
    level: CourseLevel
    semester: CourseSemester
    status: CourseStatus = CourseStatus.ACTIVE
    description: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        department_id: DepartmentId,
        code: CourseCode,
        title: CourseTitle,
        slug: CourseSlug,
        credit_units: CourseCreditUnits,
        level: CourseLevel,
        semester: CourseSemester,
        description: str | None = None,
        course_id: CourseId | None = None,
    ) -> Course:
        course = cls(
            id=course_id or CourseId(""),
            department_id=department_id,
            code=code,
            title=title,
            slug=slug,
            credit_units=credit_units,
            level=level,
            semester=semester,
            description=description,
            status=CourseStatus.ACTIVE,
        )
        course._events.append(
            DomainEvent(
                event_type="course.created",
                payload={
                    "course_id": course.id.value,
                    "department_id": course.department_id.value,
                    "code": course.code.value,
                },
            )
        )
        return course

    def archive(self) -> None:
        self.status = CourseStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course.archived",
                payload={"course_id": self.id.value},
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

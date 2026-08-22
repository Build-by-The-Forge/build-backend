from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.domain.catalogue.errors import CourseAlreadyArchivedError
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

if TYPE_CHECKING:
    from app.domain.catalogue.reference_material import ReferenceMaterial
    from app.domain.catalogue.topic import Topic


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
    topics: list["Topic"] = field(default_factory=list, repr=False)
    references: list["ReferenceMaterial"] = field(default_factory=list, repr=False)
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
        if self.status == CourseStatus.ARCHIVED:
            raise CourseAlreadyArchivedError("course already archived")
        self.status = CourseStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course.archived",
                payload={"course_id": self.id.value},
            )
        )

    def update_details(self, title: CourseTitle | None, description: str | None) -> None:
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
                event_type="course.updated",
                payload={"course_id": self.id.value},
            )
        )

    def publish(self) -> None:
        if self.status == CourseStatus.ACTIVE:
            return
        self.status = CourseStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course.published",
                payload={"course_id": self.id.value},
            )
        )

    def add_topic(self, topic: "Topic") -> None:
        if topic.course_id != self.id:
            raise ValueError("topic course_id must match the parent course")
        self.topics.append(topic)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course.topic_added",
                payload={
                    "course_id": self.id.value,
                    "topic_id": topic.id.value,
                },
            )
        )

    def add_reference(self, reference: "ReferenceMaterial") -> None:
        if reference.course_id != self.id:
            raise ValueError("reference course_id must match the parent course")
        self.references.append(reference)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="course.reference_added",
                payload={
                    "course_id": self.id.value,
                    "reference_id": reference.id.value,
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
        return self.status == CourseStatus.ACTIVE

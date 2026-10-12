from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.errors import CurriculumVersionAlreadyArchivedError
from app.domain.catalogue.value_objects import (
    CourseId,
    CurriculumVersionId,
    CurriculumVersionName,
    CurriculumVersionStatus,
    ProgrammeId,
)
from app.domain.tenant.value_objects import AcademicSessionId


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class CurriculumVersion:
    id: CurriculumVersionId
    programme_id: ProgrammeId
    name: CurriculumVersionName
    version: str
    effective_session_id: AcademicSessionId
    expires_session_id: AcademicSessionId | None = None
    status: CurriculumVersionStatus = CurriculumVersionStatus.ACTIVE
    course_ids: list[CourseId] = field(default_factory=list, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        programme_id: ProgrammeId,
        name: CurriculumVersionName,
        version: str,
        effective_session_id: AcademicSessionId,
        expires_session_id: AcademicSessionId | None = None,
        curriculum_version_id: CurriculumVersionId | None = None,
    ) -> CurriculumVersion:
        curriculum = cls(
            id=curriculum_version_id or CurriculumVersionId(""),
            programme_id=programme_id,
            name=name,
            version=version,
            effective_session_id=effective_session_id,
            expires_session_id=expires_session_id,
            status=CurriculumVersionStatus.ACTIVE,
        )
        curriculum._events.append(
            DomainEvent(
                event_type="curriculum_version.created",
                payload={
                    "curriculum_version_id": curriculum.id.value,
                    "programme_id": curriculum.programme_id.value,
                    "version": curriculum.version,
                },
            )
        )
        return curriculum

    def archive(self) -> None:
        if self.status == CurriculumVersionStatus.ARCHIVED:
            raise CurriculumVersionAlreadyArchivedError("curriculum version already archived")
        self.status = CurriculumVersionStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum_version.archived",
                payload={"curriculum_version_id": self.id.value},
            )
        )

    def publish(self) -> None:
        if self.status == CurriculumVersionStatus.ACTIVE:
            return
        self.status = CurriculumVersionStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum_version.published",
                payload={"curriculum_version_id": self.id.value},
            )
        )

    def add_course(self, course_id: CourseId) -> None:
        if course_id in self.course_ids:
            return
        self.course_ids.append(course_id)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="curriculum_version.course_added",
                payload={
                    "curriculum_version_id": self.id.value,
                    "course_id": course_id.value,
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
        return self.status == CurriculumVersionStatus.ACTIVE

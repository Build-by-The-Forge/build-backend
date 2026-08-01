from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.tenant.errors import ProgrammeAlreadyArchivedError
from app.domain.tenant.value_objects import (
    DepartmentId,
    FacultyId,
    ProgrammeCode,
    ProgrammeId,
    ProgrammeName,
    ProgrammeSlug,
    ProgrammeStatus,
    TenantId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Programme:
    id: ProgrammeId
    tenant_id: TenantId
    faculty_id: FacultyId
    department_id: DepartmentId
    name: ProgrammeName
    slug: ProgrammeSlug
    code: ProgrammeCode
    duration_years: int = 5
    status: ProgrammeStatus = ProgrammeStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        faculty_id: FacultyId,
        department_id: DepartmentId,
        name: ProgrammeName,
        slug: ProgrammeSlug,
        code: ProgrammeCode,
        duration_years: int = 5,
        programme_id: ProgrammeId | None = None,
    ) -> Programme:
        if duration_years < 1 or duration_years > 7:
            raise ValueError("duration must be 1-7 years")

        prog = cls(
            id=programme_id or ProgrammeId(""),
            tenant_id=tenant_id,
            faculty_id=faculty_id,
            department_id=department_id,
            name=name,
            slug=slug,
            code=code,
            duration_years=duration_years,
            status=ProgrammeStatus.ACTIVE,
        )
        prog._events.append(
            DomainEvent(
                event_type="programme.created",
                payload={
                    "programme_id": prog.id.value,
                    "tenant_id": prog.tenant_id.value,
                    "department_id": prog.department_id.value,
                    "slug": prog.slug.value,
                    "code": prog.code.value,
                },
            )
        )
        return prog

    def rename(self, new_name: ProgrammeName) -> None:
        if new_name.value == self.name.value:
            return
        self.name = new_name
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="programme.updated",
                payload={
                    "programme_id": self.id.value,
                    "name": self.name.value,
                },
            )
        )

    def archive(self) -> None:
        if self.status == ProgrammeStatus.ARCHIVED:
            raise ProgrammeAlreadyArchivedError("programme already archived")
        self.status = ProgrammeStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="programme.archived",
                payload={"programme_id": self.id.value},
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
        return self.status == ProgrammeStatus.ACTIVE

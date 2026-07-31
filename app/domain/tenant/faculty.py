from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.tenant.errors import FacultyAlreadyArchivedError
from app.domain.tenant.value_objects import (
    FacultyId,
    FacultyName,
    FacultySlug,
    FacultyStatus,
    TenantId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Faculty:
    id: FacultyId
    tenant_id: TenantId
    name: FacultyName
    slug: FacultySlug
    status: FacultyStatus = FacultyStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        name: FacultyName,
        slug: FacultySlug,
        faculty_id: FacultyId | None = None,
    ) -> Faculty:
        faculty = cls(
            id=faculty_id or FacultyId(""),
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            status=FacultyStatus.ACTIVE,
        )
        faculty._events.append(
            DomainEvent(
                event_type="faculty.created",
                payload={
                    "faculty_id": faculty.id.value,
                    "tenant_id": faculty.tenant_id.value,
                    "slug": faculty.slug.value,
                },
            )
        )
        return faculty

    def rename(self, new_name: FacultyName) -> None:
        if new_name.value == self.name.value:
            return
        self.name = new_name
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="faculty.updated",
                payload={
                    "faculty_id": self.id.value,
                    "name": self.name.value,
                },
            )
        )

    def archive(self) -> None:
        if self.status == FacultyStatus.ARCHIVED:
            raise FacultyAlreadyArchivedError("faculty already archived")
        self.status = FacultyStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="faculty.archived",
                payload={"faculty_id": self.id.value},
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
        return self.status == FacultyStatus.ACTIVE

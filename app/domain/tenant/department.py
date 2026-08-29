from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.tenant.errors import DepartmentAlreadyArchivedError
from app.domain.tenant.value_objects import (
    DepartmentCode,
    DepartmentId,
    DepartmentName,
    DepartmentSlug,
    DepartmentStatus,
    FacultyId,
    TenantId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Department:
    id: DepartmentId
    tenant_id: TenantId
    faculty_id: FacultyId
    name: DepartmentName
    slug: DepartmentSlug
    code: DepartmentCode | None = None
    status: DepartmentStatus = DepartmentStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        faculty_id: FacultyId,
        name: DepartmentName,
        slug: DepartmentSlug,
        code: DepartmentCode | None = None,
        department_id: DepartmentId | None = None,
    ) -> Department:
        dept = cls(
            id=department_id or DepartmentId(""),
            tenant_id=tenant_id,
            faculty_id=faculty_id,
            name=name,
            slug=slug,
            code=code,
            status=DepartmentStatus.ACTIVE,
        )
        dept._events.append(
            DomainEvent(
                event_type="department.created",
                payload={
                    "department_id": dept.id.value,
                    "tenant_id": dept.tenant_id.value,
                    "faculty_id": dept.faculty_id.value,
                    "slug": dept.slug.value,
                    "code": dept.code.value if dept.code else None,
                },
            )
        )
        return dept

    def rename(self, new_name: DepartmentName) -> None:
        if new_name.value == self.name.value:
            return
        self.name = new_name
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="department.updated",
                payload={
                    "department_id": self.id.value,
                    "name": self.name.value,
                },
            )
        )

    def change_code(self, new_code: DepartmentCode) -> None:
        self.code = new_code
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="department.updated",
                payload={
                    "department_id": self.id.value,
                    "code": self.code.value,
                },
            )
        )

    def archive(self) -> None:
        if self.status == DepartmentStatus.ARCHIVED:
            raise DepartmentAlreadyArchivedError("department already archived")
        self.status = DepartmentStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="department.archived",
                payload={"department_id": self.id.value},
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
        return self.status == DepartmentStatus.ACTIVE

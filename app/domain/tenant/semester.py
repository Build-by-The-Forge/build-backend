from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.domain.tenant.errors import SemesterAlreadyArchivedError
from app.domain.tenant.value_objects import (
    AcademicSessionId,
    SemesterId,
    SemesterName,
    SemesterNumber,
    SemesterStatus,
    TenantId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Semester:
    id: SemesterId
    tenant_id: TenantId
    academic_session_id: AcademicSessionId
    number: SemesterNumber
    name: SemesterName
    start_date: date
    end_date: date
    is_current: bool = False
    status: SemesterStatus = SemesterStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        academic_session_id: AcademicSessionId,
        number: SemesterNumber,
        name: SemesterName | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        is_current: bool = False,
        semester_id: SemesterId | None = None,
    ) -> Semester:
        if start_date and end_date and end_date <= start_date:
            raise ValueError("semester end_date must be after start_date")

        default_name = SemesterName("First Semester") if number == SemesterNumber.FIRST else SemesterName("Second Semester")

        sem = cls(
            id=semester_id or SemesterId(""),
            tenant_id=tenant_id,
            academic_session_id=academic_session_id,
            number=number,
            name=name or default_name,
            start_date=start_date or date.today(),
            end_date=end_date or date.today(),
            is_current=is_current,
            status=SemesterStatus.ACTIVE,
        )
        sem._events.append(
            DomainEvent(
                event_type="semester.created",
                payload={
                    "semester_id": sem.id.value,
                    "session_id": sem.academic_session_id.value,
                    "number": sem.number.value,
                    "is_current": sem.is_current,
                },
            )
        )
        return sem

    def mark_as_current(self) -> None:
        if self.is_current:
            return
        self.is_current = True
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="semester.current_changed",
                payload={
                    "semester_id": self.id.value,
                    "is_current": True,
                },
            )
        )

    def unmark_as_current(self) -> None:
        if not self.is_current:
            return
        self.is_current = False
        self.touch()

    def archive(self) -> None:
        if self.status == SemesterStatus.ARCHIVED:
            raise SemesterAlreadyArchivedError("semester already archived")
        self.status = SemesterStatus.ARCHIVED
        self.is_current = False
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="semester.archived",
                payload={"semester_id": self.id.value},
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
        return self.status == SemesterStatus.ACTIVE

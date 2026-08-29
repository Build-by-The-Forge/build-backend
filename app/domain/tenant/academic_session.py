from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.domain.tenant.errors import AcademicSessionAlreadyArchivedError
from app.domain.tenant.value_objects import (
    AcademicSessionId,
    AcademicSessionName,
    AcademicSessionSlug,
    AcademicSessionStatus,
    TenantId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class AcademicSession:
    id: AcademicSessionId
    tenant_id: TenantId
    name: AcademicSessionName
    slug: AcademicSessionSlug
    start_date: date
    end_date: date
    is_current: bool = False
    status: AcademicSessionStatus = AcademicSessionStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        name: AcademicSessionName,
        slug: AcademicSessionSlug,
        start_date: date,
        end_date: date,
        is_current: bool = False,
        session_id: AcademicSessionId | None = None,
    ) -> AcademicSession:
        if end_date <= start_date:
            raise ValueError("session end_date must be after start_date")

        session = cls(
            id=session_id or AcademicSessionId(""),
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            status=AcademicSessionStatus.ACTIVE,
        )
        session._events.append(
            DomainEvent(
                event_type="academic_session.created",
                payload={
                    "session_id": session.id.value,
                    "tenant_id": session.tenant_id.value,
                    "name": session.name.value,
                    "is_current": session.is_current,
                },
            )
        )
        return session

    def mark_as_current(self) -> None:
        if self.is_current:
            return
        self.is_current = True
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="academic_session.current_changed",
                payload={
                    "session_id": self.id.value,
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
        if self.status == AcademicSessionStatus.ARCHIVED:
            raise AcademicSessionAlreadyArchivedError(
                "academic session already archived"
            )
        self.status = AcademicSessionStatus.ARCHIVED
        self.is_current = False
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="academic_session.archived",
                payload={"session_id": self.id.value},
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
        return self.status == AcademicSessionStatus.ACTIVE

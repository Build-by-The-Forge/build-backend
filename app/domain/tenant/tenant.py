from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.tenant.errors import TenantAlreadyArchivedError
from app.domain.tenant.value_objects import (
    TenantId,
    TenantName,
    TenantSlug,
    TenantStatus,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Tenant:
    id: TenantId
    name: TenantName
    slug: TenantSlug
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        name: TenantName,
        slug: TenantSlug,
        tenant_id: TenantId | None = None,
    ) -> Tenant:
        tenant = cls(
            id=tenant_id or TenantId(""),
            name=name,
            slug=slug,
            status=TenantStatus.ACTIVE,
        )
        tenant._events.append(
            DomainEvent(
                event_type="tenant.created",
                payload={
                    "tenant_id": tenant.id.value,
                    "slug": tenant.slug.value,
                },
            )
        )
        return tenant

    def rename(self, new_name: TenantName) -> None:
        if new_name.value == self.name.value:
            return
        self.name = new_name
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="tenant.updated",
                payload={
                    "tenant_id": self.id.value,
                    "name": self.name.value,
                },
            )
        )

    def archive(self) -> None:
        if self.status == TenantStatus.ARCHIVED:
            raise TenantAlreadyArchivedError("tenant already archived")
        self.status = TenantStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="tenant.archived",
                payload={"tenant_id": self.id.value},
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
        return self.status == TenantStatus.ACTIVE

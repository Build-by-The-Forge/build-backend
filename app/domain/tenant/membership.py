from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.tenant.errors import MembershipAlreadyArchivedError
from app.domain.tenant.value_objects import (
    MembershipId,
    MembershipRole,
    MembershipStatus,
    TenantId,
    UserId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Membership:
    id: MembershipId
    tenant_id: TenantId
    user_id: UserId
    role: MembershipRole
    status: MembershipStatus = MembershipStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        user_id: UserId,
        role: MembershipRole,
        membership_id: MembershipId | None = None,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> Membership:
        member = cls(
            id=membership_id or MembershipId(""),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            status=status,
        )
        member._events.append(
            DomainEvent(
                event_type="membership.created",
                payload={
                    "membership_id": member.id.value,
                    "tenant_id": member.tenant_id.value,
                    "user_id": member.user_id.value,
                    "role": member.role.value,
                },
            )
        )
        return member

    def change_role(self, new_role: MembershipRole) -> None:
        if new_role == self.role:
            return
        self.role = new_role
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="membership.role_changed",
                payload={
                    "membership_id": self.id.value,
                    "role": self.role.value,
                },
            )
        )

    def archive(self) -> None:
        if self.status == MembershipStatus.ARCHIVED:
            raise MembershipAlreadyArchivedError("membership already archived")
        self.status = MembershipStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="membership.archived",
                payload={"membership_id": self.id.value},
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
        return self.status == MembershipStatus.ACTIVE

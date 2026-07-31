from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.tenant.errors import LevelAlreadyArchivedError
from app.domain.tenant.value_objects import (
    LevelCode,
    LevelId,
    LevelName,
    LevelStatus,
    TenantId,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class Level:
    id: LevelId
    tenant_id: TenantId
    code: LevelCode
    name: LevelName
    status: LevelStatus = LevelStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        tenant_id: TenantId,
        code: LevelCode,
        name: LevelName | None = None,
        level_id: LevelId | None = None,
    ) -> Level:
        lvl = cls(
            id=level_id or LevelId(""),
            tenant_id=tenant_id,
            code=code,
            name=name or LevelName(f"{code.value} Level"),
            status=LevelStatus.ACTIVE,
        )
        lvl._events.append(
            DomainEvent(
                event_type="level.created",
                payload={
                    "level_id": lvl.id.value,
                    "tenant_id": lvl.tenant_id.value,
                    "code": lvl.code.value,
                },
            )
        )
        return lvl

    def rename(self, new_name: LevelName) -> None:
        if new_name.value == self.name.value:
            return
        self.name = new_name
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="level.updated",
                payload={
                    "level_id": self.id.value,
                    "name": self.name.value,
                },
            )
        )

    def archive(self) -> None:
        if self.status == LevelStatus.ARCHIVED:
            raise LevelAlreadyArchivedError("level already archived")
        self.status = LevelStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="level.archived",
                payload={"level_id": self.id.value},
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
        return self.status == LevelStatus.ACTIVE

    @property
    def is_final_year(self) -> bool:
        return self.code.value >= 500

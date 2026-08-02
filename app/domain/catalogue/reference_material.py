from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.catalogue.errors import ReferenceMaterialAlreadyArchivedError
from app.domain.catalogue.value_objects import (
    CourseId,
    ReferenceMaterialId,
    ReferenceMaterialStatus,
    ReferenceMaterialTitle,
    ReferenceMaterialType,
    ReferenceMaterialUrl,
)


@dataclass
class DomainEvent:
    event_type: str
    payload: dict[str, Any]


@dataclass
class ReferenceMaterial:
    id: ReferenceMaterialId
    course_id: CourseId
    title: ReferenceMaterialTitle
    material_type: ReferenceMaterialType
    url: ReferenceMaterialUrl | None = None
    status: ReferenceMaterialStatus = ReferenceMaterialStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        course_id: CourseId,
        title: ReferenceMaterialTitle,
        material_type: ReferenceMaterialType,
        url: ReferenceMaterialUrl | None = None,
        reference_material_id: ReferenceMaterialId | None = None,
    ) -> ReferenceMaterial:
        material = cls(
            id=reference_material_id or ReferenceMaterialId(""),
            course_id=course_id,
            title=title,
            material_type=material_type,
            url=url,
            status=ReferenceMaterialStatus.ACTIVE,
        )
        material._events.append(
            DomainEvent(
                event_type="reference_material.created",
                payload={
                    "reference_material_id": material.id.value,
                    "course_id": course_id.value,
                },
            )
        )
        return material

    def archive(self) -> None:
        if self.status == ReferenceMaterialStatus.ARCHIVED:
            raise ReferenceMaterialAlreadyArchivedError(
                "reference material already archived"
            )
        self.status = ReferenceMaterialStatus.ARCHIVED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="reference_material.archived",
                payload={"reference_material_id": self.id.value},
            )
        )

    def publish(self) -> None:
        if self.status == ReferenceMaterialStatus.ACTIVE:
            return
        self.status = ReferenceMaterialStatus.ACTIVE
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="reference_material.published",
                payload={"reference_material_id": self.id.value},
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
        return self.status == ReferenceMaterialStatus.ACTIVE

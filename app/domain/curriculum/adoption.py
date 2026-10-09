from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.events.base import DomainEvent


class AdoptionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class OverrideType(StrEnum):
    MODIFY_COURSE = "modify_course"
    ADD_COURSE = "add_course"
    OMIT_COURSE = "omit_course"
    MODIFY_TOPIC = "modify_topic"
    ADD_TOPIC = "add_topic"
    OMIT_TOPIC = "omit_topic"
    ADD_OUTCOME = "add_outcome"
    OMIT_OUTCOME = "omit_outcome"


@dataclass(slots=True)
class CurriculumOverride:
    id: str
    adoption_id: str
    override_type: OverrideType
    reason: str
    created_by: str
    created_by_email: str
    target_course_code: str | None = None
    target_topic_id: str | None = None
    target_outcome_id: str | None = None
    field_overrides: dict[str, Any] = field(default_factory=dict)
    custom_payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        adoption_id: str,
        override_type: OverrideType | str,
        reason: str,
        created_by: str,
        created_by_email: str,
        target_course_code: str | None = None,
        target_topic_id: str | None = None,
        target_outcome_id: str | None = None,
        field_overrides: dict[str, Any] | None = None,
        custom_payload: dict[str, Any] | None = None,
        override_id: str | None = None,
    ) -> CurriculumOverride:
        if not adoption_id.strip():
            raise ValueError("adoption_id cannot be empty")
        if not reason or not reason.strip():
            raise ValueError(
                "academic rationale (reason) is mandatory for institutional overrides"
            )
        if not created_by.strip():
            raise ValueError("created_by cannot be empty")
        if not created_by_email.strip():
            raise ValueError("created_by_email cannot be empty")

        ov_type = (
            OverrideType(override_type)
            if isinstance(override_type, str)
            else override_type
        )

        norm_course_code = (
            "".join(target_course_code.split()).upper() if target_course_code else None
        )

        if (
            ov_type
            in (
                OverrideType.MODIFY_COURSE,
                OverrideType.OMIT_COURSE,
            )
            and not norm_course_code
        ):
            raise ValueError(
                f"target_course_code is required for override type '{ov_type.value}'"
            )

        if ov_type == OverrideType.ADD_COURSE:
            payload = custom_payload or {}
            required_keys = ("code", "title", "credit_units", "level", "semester")
            missing = [k for k in required_keys if k not in payload]
            if missing:
                raise ValueError(
                    f"custom_payload for add_course is missing required fields: {', '.join(missing)}"
                )

        return cls(
            id=override_id or str(uuid4()),
            adoption_id=adoption_id.strip(),
            override_type=ov_type,
            target_course_code=norm_course_code,
            target_topic_id=target_topic_id.strip() if target_topic_id else None,
            target_outcome_id=target_outcome_id.strip() if target_outcome_id else None,
            field_overrides=field_overrides or {},
            custom_payload=custom_payload or {},
            reason=reason.strip(),
            created_by=created_by.strip(),
            created_by_email=created_by_email.strip(),
            created_at=datetime.now(timezone.utc),
        )


@dataclass(slots=True)
class InstitutionalAdoption:
    id: str
    tenant_id: str
    programme_id: str
    benchmark_curriculum_id: str
    benchmark_version: str
    benchmark_fingerprint: str | None
    academic_session_id: str | None
    status: AdoptionStatus
    adopted_by: str
    adopted_by_email: str
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, init=False)

    @classmethod
    def create_draft(
        cls,
        tenant_id: str,
        programme_id: str,
        benchmark_curriculum_id: str,
        benchmark_version: str,
        adopted_by: str,
        adopted_by_email: str,
        benchmark_fingerprint: str | None = None,
        academic_session_id: str | None = None,
        notes: str | None = None,
        adoption_id: str | None = None,
    ) -> InstitutionalAdoption:
        if not tenant_id.strip():
            raise ValueError("tenant_id cannot be empty")
        if not programme_id.strip():
            raise ValueError("programme_id cannot be empty")
        if not benchmark_curriculum_id.strip():
            raise ValueError("benchmark_curriculum_id cannot be empty")
        if not benchmark_version.strip():
            raise ValueError("benchmark_version cannot be empty")
        if not adopted_by.strip():
            raise ValueError("adopted_by cannot be empty")
        if not adopted_by_email.strip():
            raise ValueError("adopted_by_email cannot be empty")

        now = datetime.now(timezone.utc)
        adoption = cls(
            id=adoption_id or str(uuid4()),
            tenant_id=tenant_id.strip(),
            programme_id=programme_id.strip(),
            benchmark_curriculum_id=benchmark_curriculum_id.strip(),
            benchmark_version=benchmark_version.strip(),
            benchmark_fingerprint=(
                benchmark_fingerprint.strip() if benchmark_fingerprint else None
            ),
            academic_session_id=(
                academic_session_id.strip() if academic_session_id else None
            ),
            status=AdoptionStatus.DRAFT,
            notes=notes.strip() if notes else None,
            adopted_by=adopted_by.strip(),
            adopted_by_email=adopted_by_email.strip(),
            created_at=now,
            updated_at=now,
        )
        adoption._record_event(
            DomainEvent(
                event_type="curriculum.adoption_created",
                payload={
                    "adoption_id": adoption.id,
                    "tenant_id": adoption.tenant_id,
                    "programme_id": adoption.programme_id,
                    "benchmark_curriculum_id": adoption.benchmark_curriculum_id,
                    "benchmark_version": adoption.benchmark_version,
                    "benchmark_fingerprint": adoption.benchmark_fingerprint,
                    "academic_session_id": adoption.academic_session_id,
                },
            )
        )
        return adoption

    def activate(self, activated_by: str | None = None) -> None:
        if self.status != AdoptionStatus.DRAFT:
            raise ValueError(
                f"only draft adoptions can be activated, current status is '{self.status.value}'"
            )
        self.status = AdoptionStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)
        self._record_event(
            DomainEvent(
                event_type="curriculum.adoption_activated",
                payload={
                    "adoption_id": self.id,
                    "tenant_id": self.tenant_id,
                    "programme_id": self.programme_id,
                    "benchmark_curriculum_id": self.benchmark_curriculum_id,
                    "benchmark_version": self.benchmark_version,
                    "activated_by": activated_by or self.adopted_by,
                },
            )
        )

    def supersede(self) -> None:
        if self.status != AdoptionStatus.ACTIVE:
            raise ValueError(
                f"only active adoptions can be superseded, current status is '{self.status.value}'"
            )
        self.status = AdoptionStatus.SUPERSEDED
        self.updated_at = datetime.now(timezone.utc)
        self._record_event(
            DomainEvent(
                event_type="curriculum.adoption_superseded",
                payload={
                    "adoption_id": self.id,
                    "tenant_id": self.tenant_id,
                    "programme_id": self.programme_id,
                    "benchmark_curriculum_id": self.benchmark_curriculum_id,
                },
            )
        )

    def archive(self) -> None:
        self.status = AdoptionStatus.ARCHIVED
        self.updated_at = datetime.now(timezone.utc)

    def is_editable(self) -> bool:
        return self.status == AdoptionStatus.DRAFT

    def _record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

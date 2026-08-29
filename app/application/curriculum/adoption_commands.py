from dataclasses import dataclass
from typing import Any

from app.domain.curriculum.adoption import OverrideType


@dataclass(slots=True)
class AdoptBenchmarkCurriculumCommand:
    tenant_id: str
    programme_id: str
    benchmark_curriculum_id: str
    actor_id: str
    actor_email: str
    academic_session_id: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class AddCurriculumOverrideCommand:
    adoption_id: str
    tenant_id: str
    override_type: OverrideType | str
    reason: str
    actor_id: str
    actor_email: str
    target_course_code: str | None = None
    target_topic_id: str | None = None
    target_outcome_id: str | None = None
    field_overrides: dict[str, Any] | None = None
    custom_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class RemoveCurriculumOverrideCommand:
    adoption_id: str
    override_id: str
    tenant_id: str


@dataclass(slots=True)
class ActivateAdoptionCommand:
    adoption_id: str
    tenant_id: str
    actor_id: str


@dataclass(slots=True)
class GetAdoptionDetailCommand:
    adoption_id: str
    tenant_id: str


@dataclass(slots=True)
class ListAdoptionsCommand:
    tenant_id: str
    programme_id: str | None = None

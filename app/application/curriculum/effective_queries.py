from dataclasses import dataclass


@dataclass(slots=True)
class GetEffectiveCurriculumByAdoptionQuery:
    adoption_id: str
    tenant_id: str


@dataclass(slots=True)
class GetActiveEffectiveCurriculumQuery:
    tenant_id: str
    programme_id: str
    academic_session_id: str | None = None

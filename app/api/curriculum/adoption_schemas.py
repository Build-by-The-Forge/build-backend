from typing import Any

from pydantic import BaseModel, Field


class AdoptBenchmarkRequest(BaseModel):
    programme_id: str
    benchmark_curriculum_id: str
    academic_session_id: str | None = None
    notes: str | None = None


class CreateOverrideRequest(BaseModel):
    override_type: str
    reason: str
    target_course_code: str | None = None
    target_topic_id: str | None = None
    target_outcome_id: str | None = None
    field_overrides: dict[str, Any] = Field(default_factory=dict)
    custom_payload: dict[str, Any] = Field(default_factory=dict)


class CurriculumOverrideResponse(BaseModel):
    id: str
    adoption_id: str
    override_type: str
    target_course_code: str | None = None
    target_topic_id: str | None = None
    target_outcome_id: str | None = None
    field_overrides: dict[str, Any] = Field(default_factory=dict)
    custom_payload: dict[str, Any] = Field(default_factory=dict)
    reason: str
    created_by: str
    created_by_email: str
    created_at: str


class InstitutionalAdoptionResponse(BaseModel):
    id: str
    tenant_id: str
    programme_id: str
    benchmark_curriculum_id: str
    benchmark_version: str
    benchmark_fingerprint: str | None = None
    academic_session_id: str | None = None
    status: str
    notes: str | None = None
    adopted_by: str
    adopted_by_email: str
    created_at: str
    updated_at: str


class AdoptionDetailResponse(BaseModel):
    adoption: InstitutionalAdoptionResponse
    overrides: list[CurriculumOverrideResponse] = Field(default_factory=list)

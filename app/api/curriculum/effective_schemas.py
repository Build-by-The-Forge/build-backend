from typing import Any

from pydantic import BaseModel, Field


class AppliedOverrideProvenanceResponse(BaseModel):
    override_id: str
    override_type: str
    reason: str
    field_overrides: dict[str, Any] = Field(default_factory=dict)
    created_by_email: str
    created_at: str


class EffectiveOutcomeResponse(BaseModel):
    id: str
    sequence: int
    description: str
    bloom_level: str
    origin: str
    applied_overrides: list[AppliedOverrideProvenanceResponse] = Field(default_factory=list)


class EffectiveTopicResponse(BaseModel):
    id: str
    sequence: int
    title: str
    description: str | None = None
    origin: str
    outcomes: list[EffectiveOutcomeResponse] = Field(default_factory=list)
    applied_overrides: list[AppliedOverrideProvenanceResponse] = Field(default_factory=list)


class EffectiveCourseResponse(BaseModel):
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    sequence: int
    is_compulsory: bool
    course_category: str
    description: str | None = None
    origin: str
    topics: list[EffectiveTopicResponse] = Field(default_factory=list)
    applied_overrides: list[AppliedOverrideProvenanceResponse] = Field(default_factory=list)
    benchmark_course_id: str | None = None


class OmittedCourseResponse(BaseModel):
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    reason: str
    override_id: str
    created_by_email: str
    benchmark_course_id: str


class EffectiveCurriculumStatisticsResponse(BaseModel):
    total_credit_units: int
    total_courses: int
    national_courses_count: int
    modified_courses_count: int
    custom_courses_count: int
    omitted_courses_count: int


class EffectiveCurriculumResponse(BaseModel):
    adoption_id: str
    tenant_id: str
    programme_id: str
    academic_session_id: str | None = None
    benchmark_curriculum_id: str
    benchmark_version: str
    benchmark_fingerprint: str | None = None
    effective_curriculum_fingerprint: str
    resolution_engine_version: str
    status: str
    statistics: EffectiveCurriculumStatisticsResponse
    courses: list[EffectiveCourseResponse] = Field(default_factory=list)
    omitted_courses: list[OmittedCourseResponse] = Field(default_factory=list)


# Student Read Mode projection (educational metadata without internal admin details)
class StudentOutcomeResponse(BaseModel):
    sequence: int
    description: str
    bloom_level: str


class StudentTopicResponse(BaseModel):
    sequence: int
    title: str
    description: str | None = None
    outcomes: list[StudentOutcomeResponse] = Field(default_factory=list)


class StudentCourseResponse(BaseModel):
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    is_compulsory: bool
    course_category: str
    description: str | None = None
    origin: str
    topics: list[StudentTopicResponse] = Field(default_factory=list)


class StudentEffectiveCurriculumResponse(BaseModel):
    programme_id: str
    academic_session_id: str | None = None
    benchmark_version: str
    effective_curriculum_fingerprint: str
    total_credit_units: int
    total_courses: int
    courses: list[StudentCourseResponse] = Field(default_factory=list)

from pydantic import BaseModel, Field


class IngestBenchmarkOutcomeRequest(BaseModel):
    sequence: int = Field(..., ge=1)
    description: str = Field(..., min_length=2)
    bloom_level: str | None = None


class IngestBenchmarkTopicRequest(BaseModel):
    sequence: int = Field(..., ge=1)
    title: str = Field(..., min_length=2, max_length=200)
    description: str | None = None
    outcomes: list[IngestBenchmarkOutcomeRequest] = Field(default_factory=list)


class IngestBenchmarkCourseRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    title: str = Field(..., min_length=2, max_length=200)
    credit_units: int = Field(..., ge=1, le=12)
    level: int = Field(..., ge=100, le=600)
    semester: int = Field(..., ge=1, le=2)
    sequence: int = Field(..., ge=1)
    is_compulsory: bool = True
    course_category: str = "core"
    description: str | None = None
    topics: list[IngestBenchmarkTopicRequest] = Field(default_factory=list)


class IngestBenchmarkCandidateRequest(BaseModel):
    source_snapshot_id: str = Field(..., min_length=1)
    extractor_version: str = Field(..., min_length=1)
    discipline_group: str = Field(..., min_length=2, max_length=100)
    programme_name: str = Field(..., min_length=2, max_length=150)
    programme_code: str = Field(..., min_length=2, max_length=30)
    version: str = Field(..., min_length=1, max_length=50)
    degree_level: str = "undergraduate"
    minimum_credit_units: int = 120
    courses: list[IngestBenchmarkCourseRequest] = Field(default_factory=list)


class BenchmarkCurriculumSummaryResponse(BaseModel):
    id: str
    source_snapshot_id: str
    discipline_group: str
    programme_name: str
    programme_code: str
    degree_level: str
    version: str
    minimum_credit_units: int
    status: str
    created_at: str
    updated_at: str


class BenchmarkOutcomeResponse(BaseModel):
    id: str
    sequence: int
    description: str
    bloom_level: str | None = None


class BenchmarkTopicResponse(BaseModel):
    id: str
    sequence: int
    title: str
    description: str | None = None
    outcomes: list[BenchmarkOutcomeResponse] = Field(default_factory=list)


class BenchmarkCourseSummaryResponse(BaseModel):
    id: str
    benchmark_curriculum_id: str
    code: str
    title: str
    credit_units: int
    level: int
    semester: int
    is_compulsory: bool
    course_category: str
    description: str | None = None
    sequence: int


class BenchmarkCourseDetailResponse(BenchmarkCourseSummaryResponse):
    topics: list[BenchmarkTopicResponse] = Field(default_factory=list)


class ValidationIssueResponse(BaseModel):
    entity_type: str
    entity_identifier: str
    field: str
    rule: str
    message: str
    severity: str


class ValidationResultResponse(BaseModel):
    is_valid: bool
    error_count: int
    warning_count: int
    issues: list[ValidationIssueResponse] = Field(default_factory=list)


class BenchmarkValidationResponse(BaseModel):
    curriculum: BenchmarkCurriculumSummaryResponse
    validation: ValidationResultResponse


class BenchmarkActivationResponse(BaseModel):
    activated: BenchmarkCurriculumSummaryResponse
    superseded: BenchmarkCurriculumSummaryResponse | None = None


class FieldDiffResponse(BaseModel):
    field: str
    old_value: object | None = None
    new_value: object | None = None


class OutcomeDiffResponse(BaseModel):
    sequence: int
    action: str
    description: str
    field_diffs: list[FieldDiffResponse] = Field(default_factory=list)


class TopicDiffResponse(BaseModel):
    sequence: int
    title: str
    action: str
    field_diffs: list[FieldDiffResponse] = Field(default_factory=list)
    outcome_diffs: list[OutcomeDiffResponse] = Field(default_factory=list)


class CourseDiffResponse(BaseModel):
    code: str
    title: str
    action: str
    field_diffs: list[FieldDiffResponse] = Field(default_factory=list)
    topic_diffs: list[TopicDiffResponse] = Field(default_factory=list)


class DiffStatisticsResponse(BaseModel):
    courses_added: int
    courses_removed: int
    courses_modified: int
    topics_added: int
    topics_removed: int
    topics_modified: int
    outcomes_added: int
    outcomes_removed: int
    outcomes_modified: int
    credit_units_before: int
    credit_units_after: int
    credit_units_delta: int


class BenchmarkCurriculumDiffResponse(BaseModel):
    source_curriculum_id: str
    target_curriculum_id: str
    source_version: str
    target_version: str
    discipline_group: str
    programme_code: str
    degree_level: str
    diff_fingerprint: str
    statistics: DiffStatisticsResponse
    course_diffs: list[CourseDiffResponse] = Field(default_factory=list)


class SubmitReviewRequest(BaseModel):
    notes: str | None = None


class ApproveBenchmarkRequest(BaseModel):
    reason: str


class RejectBenchmarkRequest(BaseModel):
    reason: str


class ReviseBenchmarkRequest(BaseModel):
    reason: str | None = None


class BenchmarkAuditLogResponse(BaseModel):
    id: str
    curriculum_id: str
    action: str
    actor_id: str
    actor_email: str
    previous_status: str
    new_status: str
    reason: str | None = None
    review_notes: str | None = None
    diff_fingerprint: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str


class BenchmarkGovernanceActionResponse(BaseModel):
    curriculum: BenchmarkCurriculumSummaryResponse
    audit_log: BenchmarkAuditLogResponse

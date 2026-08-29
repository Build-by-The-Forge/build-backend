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

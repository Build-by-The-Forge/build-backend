from pydantic import BaseModel, Field


class CreateCurriculumSourceRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, examples=["NUC_CCMAS"])
    name: str = Field(..., min_length=2, max_length=200, examples=["NUC Core Curriculum Standards"])
    base_url: str = Field(..., min_length=5, max_length=1024)
    source_type: str = Field(default="official_benchmark", max_length=50)
    sync_frequency_days: int = Field(default=30, ge=1, le=365)
    parser_version: str = Field(default="v1.0", max_length=50)


class CurriculumSourceResponse(BaseModel):
    id: str
    code: str
    name: str
    base_url: str
    source_type: str
    status: str
    sync_frequency_days: int
    parser_version: str
    created_at: str
    updated_at: str


class CurriculumSnapshotResponse(BaseModel):
    id: str
    source_id: str
    source_url: str
    retrieved_at: str
    content_sha256: str
    parser_version: str
    status: str
    created_at: str


class CurriculumSyncTriggerResponse(BaseModel):
    job_id: str
    status: str

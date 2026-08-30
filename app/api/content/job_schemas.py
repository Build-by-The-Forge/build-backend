from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.content.job import ContentIngestionJob


class IngestionJobCreateRequest(BaseModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    correlation_id: str | None = None


class IngestionJobProgressRequest(BaseModel):
    target_stage: str = Field(..., pattern="^(extracted|chunked|indexed)$")
    metrics: dict[str, Any] = Field(default_factory=dict)


class IngestionJobCompleteRequest(BaseModel):
    metrics: dict[str, Any] = Field(default_factory=dict)


class IngestionJobFailRequest(BaseModel):
    error_code: str = Field(..., min_length=1, max_length=100)
    error_message: str = Field(..., min_length=1)
    is_retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class IngestionJobRetryRequest(BaseModel):
    delay_seconds: int = Field(default=30, ge=1, le=3600)


class IngestionJobReprocessRequest(BaseModel):
    correlation_id: str | None = None


class IngestionJobResponse(BaseModel):
    id: str
    asset_id: str
    source_id: str
    tenant_id: str | None = None
    run_number: int
    status: str
    current_stage: str | None = None
    attempt_count: int
    max_attempts: int
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] = Field(default_factory=dict)
    is_retryable: bool = False
    next_retry_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    attempt_history: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str | None = None
    external_task_id: str | None = None
    last_dispatched_at: datetime | None = None
    last_callback_at: datetime | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, job: ContentIngestionJob) -> IngestionJobResponse:
        return cls(
            id=job.id,
            asset_id=job.asset_id,
            source_id=job.source_id,
            tenant_id=job.tenant_id,
            run_number=job.run_number,
            status=job.status.value,
            current_stage=job.current_stage,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            error_code=job.error_code,
            error_message=job.error_message,
            error_details=job.error_details,
            is_retryable=job.is_retryable,
            next_retry_at=job.next_retry_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            metrics=job.metrics,
            attempt_history=job.attempt_history,
            correlation_id=job.correlation_id,
            external_task_id=job.external_task_id,
            last_dispatched_at=job.last_dispatched_at,
            last_callback_at=job.last_callback_at,
            created_by=job.created_by,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

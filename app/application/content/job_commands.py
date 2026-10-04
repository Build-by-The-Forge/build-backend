from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.content.enums import IngestionStatus


@dataclass(frozen=True, slots=True)
class CreateIngestionJobCommand:
    asset_id: str
    tenant_id: str
    created_by: str
    max_attempts: int = 3
    correlation_id: str | None = None
    job_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetryIngestionJobCommand:
    job_id: str
    tenant_id: str
    delay_seconds: int = 30


@dataclass(frozen=True, slots=True)
class ReprocessAssetCommand:
    asset_id: str
    tenant_id: str
    created_by: str
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class DispatchIngestionJobCommand:
    job_id: str
    tenant_id: str


@dataclass(frozen=True, slots=True)
class HandleAICallbackCommand:
    job_id: str
    event_id: str
    event_type: str  # "stage_progress" | "job_completed" | "job_failed"
    stage: str | None = None  # "extracted" | "chunked" | "indexed"
    external_task_id: str | None = None
    run_number: int | None = None
    attempt_count: int | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    is_retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GetIngestionJobQuery:
    job_id: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetLatestJobForAssetQuery:
    asset_id: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class ListIngestionJobsQuery:
    tenant_id: str | None = None
    asset_id: str | None = None
    source_id: str | None = None
    status: IngestionStatus | None = None
    limit: int = 50
    offset: int = 0

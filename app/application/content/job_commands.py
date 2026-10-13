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
    user_id: str
    membership_id: str
    role: str
    # The permission the caller was authorized with; forwarded as the only
    # permission in the signed context (decision E.6).
    permission: str


@dataclass(frozen=True, slots=True)
class HandleAICallbackCommand:
    job_id: str
    # The signed system context's tenant: a callback may only touch a job of
    # that tenant (design B.3 step 3).
    tenant_id: str
    event_id: str
    event_type: str  # "stage_progress" | "job_completed" | "job_failed"
    # The attempt the event belongs to; must be the job's active attempt.
    external_task_id: str
    run_number: int
    attempt_count: int
    stage: str | None = None  # "extracted" | "chunked" | "indexed"
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


@dataclass(frozen=True, slots=True)
class ReconcileIngestionJobCommand:
    """Bring a job up to date with AI-service's account of its active task."""

    job_id: str
    tenant_id: str

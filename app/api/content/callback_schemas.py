from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AICallbackRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., pattern="^(stage_progress|job_completed|job_failed)$")
    stage: str | None = None
    external_task_id: str | None = None
    run_number: int | None = None
    attempt_count: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    is_retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AICallbackResponse(BaseModel):
    status: str = "accepted"
    job_id: str
    already_processed: bool = False

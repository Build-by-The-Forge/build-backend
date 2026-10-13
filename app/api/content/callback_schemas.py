from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Metrics and details are stored as data, never interpreted (design B.3).
MAX_CALLBACK_DATA_BYTES = 64 * 1024


class AICallbackRequest(BaseModel):
    """Body of a signed AI-service callback (design B.3).

    It names no tenant, user or role: the tenant is the signed system
    context's. Unknown fields are rejected, and the task identity
    (external_task_id, run_number, attempt_count) is required.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    event_type: Literal["stage_progress", "job_completed", "job_failed"]
    stage: Literal["extracted", "chunked", "indexed"] | None = None
    external_task_id: str = Field(..., min_length=1)
    run_number: int = Field(..., ge=1)
    attempt_count: int = Field(..., ge=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=2000)
    is_retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _bounded_data(self) -> "AICallbackRequest":
        size = len(json.dumps(self.metrics)) + len(json.dumps(self.details))
        if size > MAX_CALLBACK_DATA_BYTES:
            raise ValueError("metrics and details exceed 64 KiB")
        return self


class AICallbackResponse(BaseModel):
    status: str = "accepted"
    job_id: str
    # applied | duplicate | stale | superseded (409 not_allowed / conflict)
    outcome: str
    already_processed: bool = False

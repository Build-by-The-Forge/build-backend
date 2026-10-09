"""The processed-callback ledger (M3-08).

Every logical AI-service event (event_id) that the backend handled is
recorded once, with a digest of its canonical content and the outcome it
had. Redelivery of the same content is idempotent; the same event_id with
different content is an integrity failure.

Three identifiers are deliberately kept apart:
- the HTTP request id identifies one signed delivery (replay protection);
- the event_id identifies one logical event, stable across redeliveries;
- (run_number, attempt_count, external_task_id) identifies the attempt the
  event belongs to.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.content.job import CallbackOutcome


@dataclass(frozen=True)
class IngestionEventRecord:
    event_id: str
    job_id: str
    tenant_id: str | None
    run_number: int | None
    attempt_count: int | None
    external_task_id: str | None
    event_type: str | None
    stage: str | None
    # None only for events recorded before M3-08, whose content is unknown.
    payload_sha256: str | None
    outcome: CallbackOutcome
    received_at: datetime


def canonical_event_digest(
    *,
    job_id: str,
    event_type: str,
    run_number: int,
    attempt_count: int,
    external_task_id: str,
    stage: str | None,
    metrics: dict[str, Any],
    error_code: str | None,
    error_message: str | None,
    is_retryable: bool,
    details: dict[str, Any],
) -> str:
    """SHA-256 of the validated event in a canonical form: sorted keys,
    compact separators, ASCII. Formatting or key order on the wire cannot
    change it; any change of meaning does."""
    content = {
        "job_id": job_id,
        "event_type": event_type,
        "run_number": run_number,
        "attempt_count": attempt_count,
        "external_task_id": external_task_id,
        "stage": stage,
        "metrics": metrics,
        "error_code": error_code,
        "error_message": error_message,
        "is_retryable": is_retryable,
        "details": details,
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()

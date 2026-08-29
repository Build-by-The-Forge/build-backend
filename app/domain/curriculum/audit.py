from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class BenchmarkAuditAction(StrEnum):
    SUBMIT_REVIEW = "submit_review"
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"
    ACTIVATE = "activate"
    SUPERSEDE = "supersede"


@dataclass(slots=True)
class BenchmarkAuditLog:
    id: str
    curriculum_id: str
    action: BenchmarkAuditAction
    actor_id: str
    actor_email: str
    previous_status: str
    new_status: str
    reason: str | None = None
    review_notes: str | None = None
    diff_fingerprint: str | None = None
    metadata_payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        curriculum_id: str,
        action: BenchmarkAuditAction,
        actor_id: str,
        actor_email: str,
        previous_status: str,
        new_status: str,
        reason: str | None = None,
        review_notes: str | None = None,
        diff_fingerprint: str | None = None,
        metadata_payload: dict[str, Any] | None = None,
        log_id: str | None = None,
    ) -> BenchmarkAuditLog:
        if not curriculum_id.strip():
            raise ValueError("curriculum_id cannot be empty")
        if not actor_id.strip():
            raise ValueError("actor_id cannot be empty")
        if not actor_email.strip():
            raise ValueError("actor_email cannot be empty")

        return cls(
            id=log_id or f"bmaudit-{uuid4()}",
            curriculum_id=curriculum_id.strip(),
            action=action,
            actor_id=actor_id.strip(),
            actor_email=actor_email.strip(),
            previous_status=previous_status,
            new_status=new_status,
            reason=reason.strip() if reason else None,
            review_notes=review_notes.strip() if review_notes else None,
            diff_fingerprint=diff_fingerprint.strip() if diff_fingerprint else None,
            metadata_payload=metadata_payload or {},
            created_at=datetime.now(timezone.utc),
        )

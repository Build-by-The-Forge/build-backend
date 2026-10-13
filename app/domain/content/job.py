"""The content ingestion job and its state machine (M3 design B.3, M3-08).

Statuses: uploaded -> queued -> processing -> extracted -> chunked -> indexed
-> ready, and failed. The backend owns every transition:

* business operations (create, dispatch, retry, reprocess) run on the
  backend's own authority;
* processing events arrive as signed AI-service callbacks and are applied
  by ``apply_callback`` only for the active attempt, only in order, and only
  with the evidence each stage requires.

A job reaches ``ready`` only after the active attempt has been extracted,
chunked and indexed, and a completion event then arrives. A signature
proves who reported an event; these rules decide whether it may change the
job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.domain.content.enums import IngestionStatus
from app.events.base import DomainEvent


class InvalidJobTransition(ValueError):
    """The requested change is not allowed from the job's current state."""

    status_code = 409  # a client-side conflict, logged as routine


class RetryNotDue(InvalidJobTransition):
    """A retried attempt may not be dispatched before next_retry_at."""


class InvalidStageEvidence(ValueError):
    """A stage event lacks the evidence that stage requires."""

    status_code = 422


class CallbackOutcome(StrEnum):
    """What a processing event did. Recorded per logical event (event_id)."""

    APPLIED = "applied"  # the transition was made
    DUPLICATE = "duplicate"  # same event_id, same content: already handled
    STALE = "stale"  # for an attempt or run that is not the active one
    SUPERSEDED = "superseded"  # active attempt already at or past this point
    NOT_ALLOWED = "not_allowed"  # invalid for the current state; not consumed
    CONFLICT = "conflict"  # same event_id, different content
    LEGACY = "legacy"  # recorded before M3-08, content unknown


# How far the active attempt has progressed, for ordering stage events.
_PROGRESS = {
    IngestionStatus.PROCESSING: 0,
    IngestionStatus.EXTRACTED: 1,
    IngestionStatus.CHUNKED: 2,
    IngestionStatus.INDEXED: 3,
    IngestionStatus.READY: 4,
}
_STAGE_RANK = {"extracted": 1, "chunked": 2, "indexed": 3}
ACTIVE_STATUSES = frozenset(
    {
        IngestionStatus.PROCESSING,
        IngestionStatus.EXTRACTED,
        IngestionStatus.CHUNKED,
        IngestionStatus.INDEXED,
    }
)
_EXTRACTION_METHODS = frozenset({"native_text", "ocr"})


def _count(metrics: dict[str, Any], key: str, minimum: int) -> int:
    value = metrics.get(key)
    if type(value) is not int or value < minimum:
        raise InvalidStageEvidence(f"metrics.{key} must be an integer >= {minimum}")
    return value


def validate_stage_evidence(
    stage: str, metrics: dict[str, Any], recorded: dict[str, Any]
) -> None:
    """The evidence each stage must carry (M3-08 stage contract)."""
    if stage == "extracted":
        _count(metrics, "characters", 1)
        _count(metrics, "pages", 0)
        if metrics.get("method") not in _EXTRACTION_METHODS:
            raise InvalidStageEvidence("metrics.method must be 'native_text' or 'ocr'")
    elif stage == "chunked":
        _count(metrics, "chunks", 1)
    elif stage == "indexed":
        indexed = _count(metrics, "indexed_chunks", 1)
        if indexed != recorded.get("chunks"):
            raise InvalidStageEvidence(
                "metrics.indexed_chunks must equal the chunk count reported at chunking"
            )
        index = metrics.get("index")
        if not isinstance(index, str) or not index.strip():
            raise InvalidStageEvidence("metrics.index must name the durable index")
    else:
        raise InvalidStageEvidence(f"unknown stage {stage!r}")


@dataclass
class ContentIngestionJob:
    id: str
    asset_id: str
    source_id: str
    status: IngestionStatus
    created_by: str
    tenant_id: str | None = None
    run_number: int = 1
    current_stage: str | None = None
    attempt_count: int = 1
    max_attempts: int = 3
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] = field(default_factory=dict)
    is_retryable: bool = False
    next_retry_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    attempt_history: list[dict[str, Any]] = field(default_factory=list)
    correlation_id: str | None = None
    external_task_id: str | None = None
    last_dispatched_at: datetime | None = None
    last_callback_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        asset_id: str,
        source_id: str,
        created_by: str,
        tenant_id: str | None = None,
        run_number: int = 1,
        max_attempts: int = 3,
        correlation_id: str | None = None,
        job_id: str | None = None,
    ) -> ContentIngestionJob:
        if not asset_id.strip():
            raise ValueError("asset_id cannot be empty")
        if not source_id.strip():
            raise ValueError("source_id cannot be empty")
        if not created_by.strip():
            raise ValueError("created_by cannot be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if run_number < 1:
            raise ValueError("run_number must be at least 1")

        now = datetime.now(timezone.utc)
        job = cls(
            id=job_id or str(uuid4()),
            asset_id=asset_id.strip(),
            source_id=source_id.strip(),
            tenant_id=tenant_id.strip() if tenant_id else None,
            run_number=run_number,
            status=IngestionStatus.UPLOADED,
            created_by=created_by.strip(),
            max_attempts=max_attempts,
            correlation_id=correlation_id.strip() if correlation_id else None,
            created_at=now,
            updated_at=now,
        )

        job._events.append(
            DomainEvent(
                event_type="content.ingestion_job_created",
                payload={
                    "job_id": job.id,
                    "asset_id": job.asset_id,
                    "source_id": job.source_id,
                    "tenant_id": job.tenant_id,
                    "run_number": job.run_number,
                    "status": job.status.value,
                },
            )
        )
        return job

    def queue(self) -> None:
        """uploaded -> queued, when a job is created or a run is reprocessed.
        A failed job is requeued only through ``schedule_retry``."""
        if self.status == IngestionStatus.QUEUED:
            return
        if self.status != IngestionStatus.UPLOADED:
            raise InvalidJobTransition(
                f"Cannot queue job in status '{self.status.value}'. Must be UPLOADED."
            )

        self.status = IngestionStatus.QUEUED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_queued",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "attempt_count": self.attempt_count,
                },
            )
        )

    def ensure_dispatchable(self, now: datetime | None = None) -> None:
        """A job is dispatched only while queued and, after a retry, only once
        its retry delay has elapsed."""
        if self.status != IngestionStatus.QUEUED:
            raise InvalidJobTransition(
                f"Cannot dispatch job in status '{self.status.value}'. Must be QUEUED."
            )
        now = now or datetime.now(timezone.utc)
        retry_at = self.next_retry_at
        if retry_at is not None and retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)  # stored as UTC
        if retry_at is not None and now < retry_at:
            raise RetryNotDue(
                f"Retry attempt {self.attempt_count} may not be dispatched before "
                f"{retry_at.isoformat()}"
            )

    def record_dispatch(self, external_task_id: str) -> None:
        """queued -> processing: AI-service accepted the dispatch. The task id
        identifies this attempt from now on."""
        self.ensure_dispatchable()
        task_id = external_task_id.strip()
        if not task_id:
            raise InvalidJobTransition("An accepted dispatch must carry a task id.")

        now = datetime.now(timezone.utc)
        self.status = IngestionStatus.PROCESSING
        self.current_stage = "dispatched_to_ai"
        self.external_task_id = task_id
        self.last_dispatched_at = now
        self.next_retry_at = None
        if self.started_at is None:
            self.started_at = now
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_dispatched",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "external_task_id": self.external_task_id,
                    "attempt_count": self.attempt_count,
                    "run_number": self.run_number,
                },
            )
        )

    def _advance(self, to: IngestionStatus, stage: str, metrics: dict[str, Any]) -> None:
        self.status = to
        self.current_stage = stage
        self.metrics.update(metrics)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_stage_completed",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "stage": to.value,
                    "metrics": dict(self.metrics),
                },
            )
        )

    def progress_to_extracted(self, metrics: dict[str, Any]) -> None:
        if self.status != IngestionStatus.PROCESSING:
            raise InvalidJobTransition(
                f"Cannot transition to EXTRACTED from status '{self.status.value}'. Must be PROCESSING."
            )
        validate_stage_evidence("extracted", metrics, self.metrics)
        self._advance(IngestionStatus.EXTRACTED, "extraction_completed", metrics)

    def progress_to_chunked(self, metrics: dict[str, Any]) -> None:
        if self.status != IngestionStatus.EXTRACTED:
            raise InvalidJobTransition(
                f"Cannot transition to CHUNKED from status '{self.status.value}'. Must be EXTRACTED."
            )
        validate_stage_evidence("chunked", metrics, self.metrics)
        self._advance(IngestionStatus.CHUNKED, "chunking_completed", metrics)

    def progress_to_indexed(self, metrics: dict[str, Any]) -> None:
        if self.status != IngestionStatus.CHUNKED:
            raise InvalidJobTransition(
                f"Cannot transition to INDEXED from status '{self.status.value}'. Must be CHUNKED."
            )
        validate_stage_evidence("indexed", metrics, self.metrics)
        self._advance(IngestionStatus.INDEXED, "indexing_completed", metrics)

    def complete(self, metrics: dict[str, Any] | None = None) -> None:
        if self.status != IngestionStatus.INDEXED:
            raise InvalidJobTransition(
                f"Cannot complete job in status '{self.status.value}'. Must be INDEXED."
            )

        self.status = IngestionStatus.READY
        self.current_stage = "ready"
        self.completed_at = datetime.now(timezone.utc)
        if metrics:
            self.metrics.update(metrics)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_completed",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "run_number": self.run_number,
                    "metrics": dict(self.metrics),
                },
            )
        )

    def fail_dispatch(self, error_code: str, error_message: str, is_retryable: bool) -> None:
        """queued -> failed: the dispatch itself failed (backend business
        operation)."""
        if self.status != IngestionStatus.QUEUED:
            raise InvalidJobTransition(
                f"A dispatch failure applies to a QUEUED job, not '{self.status.value}'."
            )
        self._record_failure(error_code, error_message, is_retryable, {})

    def fail_processing(
        self,
        error_code: str,
        error_message: str,
        is_retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        """processing..indexed -> failed: AI-service reported the active
        attempt failed."""
        if self.status not in ACTIVE_STATUSES:
            raise InvalidJobTransition(
                f"A processing failure applies to an active job, not '{self.status.value}'."
            )
        self._record_failure(error_code, error_message, is_retryable, details or {})

    def _record_failure(
        self,
        error_code: str,
        error_message: str,
        is_retryable: bool,
        details: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        self.status = IngestionStatus.FAILED
        self.error_code = error_code.strip()
        self.error_message = error_message.strip()
        self.is_retryable = is_retryable
        self.error_details = dict(details)
        self.attempt_history.append(
            {
                "attempt": self.attempt_count,
                "external_task_id": self.external_task_id,
                "stage_at_failure": self.current_stage,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "error_details": self.error_details,
                "is_retryable": self.is_retryable,
                "failed_at": now.isoformat(),
            }
        )
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_failed",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "attempt": self.attempt_count,
                    "error_code": self.error_code,
                    "is_retryable": self.is_retryable,
                },
            )
        )

    def schedule_retry(self, delay_seconds: int = 30) -> None:
        """failed -> queued for a new attempt. The previous task id is cleared,
        so nothing from the failed attempt can match the new one."""
        if self.status != IngestionStatus.FAILED:
            raise InvalidJobTransition(
                f"Cannot schedule retry for job in status '{self.status.value}'. Must be FAILED."
            )
        if not self.is_retryable:
            raise InvalidJobTransition("Cannot retry a non-retryable failure.")
        if self.attempt_count >= self.max_attempts:
            raise InvalidJobTransition(
                f"Maximum attempts ({self.max_attempts}) exceeded. Terminal failure."
            )

        self.attempt_count += 1
        now = datetime.now(timezone.utc)
        self.next_retry_at = now + timedelta(seconds=delay_seconds)
        self.status = IngestionStatus.QUEUED
        self.current_stage = f"retry_attempt_{self.attempt_count}"
        self.external_task_id = None
        self.touch()

        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_retry_scheduled",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "attempt": self.attempt_count,
                    "next_retry_at": self.next_retry_at.isoformat(),
                },
            )
        )

    def is_active_attempt(self, run_number: int, attempt_count: int, external_task_id: str) -> bool:
        """The event belongs to the attempt the backend is currently running."""
        return (
            self.external_task_id is not None
            and run_number == self.run_number
            and attempt_count == self.attempt_count
            and external_task_id == self.external_task_id
        )

    def apply_callback(
        self,
        *,
        event_type: str,
        run_number: int,
        attempt_count: int,
        external_task_id: str,
        stage: str | None = None,
        metrics: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        is_retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> CallbackOutcome:
        """Apply one verified processing event (design B.3 table).

        Returns STALE for any other attempt or run, SUPERSEDED when the active
        attempt has already legitimately reached or passed this point,
        NOT_ALLOWED when the event is out of order or after a terminal state,
        and APPLIED when the transition was made. Raises InvalidStageEvidence
        when a stage lacks its required evidence.
        """
        if not self.is_active_attempt(run_number, attempt_count, external_task_id):
            return CallbackOutcome.STALE
        metrics = metrics or {}
        progress = _PROGRESS.get(self.status)

        if event_type == "stage_progress":
            rank = _STAGE_RANK.get(stage or "")
            if rank is None:
                raise InvalidStageEvidence(f"unknown stage {stage!r}")
            if progress is None:  # failed (or not yet dispatched)
                return CallbackOutcome.NOT_ALLOWED
            if progress >= rank:
                return CallbackOutcome.SUPERSEDED
            if progress != rank - 1:
                return CallbackOutcome.NOT_ALLOWED
            {
                "extracted": self.progress_to_extracted,
                "chunked": self.progress_to_chunked,
                "indexed": self.progress_to_indexed,
            }[stage or ""](metrics)
        elif event_type == "job_completed":
            if self.status == IngestionStatus.READY:
                return CallbackOutcome.SUPERSEDED
            if self.status != IngestionStatus.INDEXED:
                return CallbackOutcome.NOT_ALLOWED
            self.complete(metrics)
        elif event_type == "job_failed":
            if self.status == IngestionStatus.FAILED:
                return CallbackOutcome.SUPERSEDED
            if self.status not in ACTIVE_STATUSES:
                return CallbackOutcome.NOT_ALLOWED
            self.fail_processing(
                error_code=error_code or "AI_PROCESSING_FAILED",
                error_message=error_message or "AI-service reported job failure",
                is_retryable=is_retryable,
                details=details,
            )
        else:
            raise InvalidStageEvidence(f"unknown event type {event_type!r}")

        self.last_callback_at = datetime.now(timezone.utc)
        return CallbackOutcome.APPLIED

    def create_reprocess_run(
        self, created_by: str, correlation_id: str | None = None
    ) -> ContentIngestionJob:
        if self.status not in (IngestionStatus.READY, IngestionStatus.FAILED):
            raise InvalidJobTransition(
                f"Cannot reprocess job in active status '{self.status.value}'. Must be READY or FAILED."
            )

        new_job = ContentIngestionJob.create(
            asset_id=self.asset_id,
            source_id=self.source_id,
            tenant_id=self.tenant_id,
            created_by=created_by,
            run_number=self.run_number + 1,
            max_attempts=self.max_attempts,
            correlation_id=correlation_id or self.correlation_id,
        )
        new_job.queue()
        return new_job

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

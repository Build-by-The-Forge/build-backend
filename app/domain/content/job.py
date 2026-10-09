from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.domain.content.enums import IngestionStatus
from app.events.base import DomainEvent


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
    processed_event_ids: list[str] = field(default_factory=list)
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
        if self.status == IngestionStatus.QUEUED:
            return
        if self.status not in (IngestionStatus.UPLOADED, IngestionStatus.FAILED):
            raise ValueError(
                f"Cannot queue job in status '{self.status.value}'. Must be UPLOADED or FAILED."
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

    def record_dispatch(self, external_task_id: str) -> None:
        if self.status != IngestionStatus.QUEUED:
            raise ValueError(
                f"Cannot dispatch job in status '{self.status.value}'. Must be QUEUED."
            )

        now = datetime.now(timezone.utc)
        self.status = IngestionStatus.PROCESSING
        self.current_stage = "dispatched_to_ai"
        self.external_task_id = external_task_id.strip()
        self.last_dispatched_at = now
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

    def start(self, stage: str = "parsing") -> None:
        if self.status not in (IngestionStatus.QUEUED, IngestionStatus.PROCESSING):
            raise ValueError(
                f"Cannot start job in status '{self.status.value}'. Must be QUEUED or PROCESSING."
            )

        self.status = IngestionStatus.PROCESSING
        self.current_stage = stage
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_started",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "stage": self.current_stage,
                    "attempt_count": self.attempt_count,
                },
            )
        )

    def progress_to_extracted(self, metrics: dict[str, Any] | None = None) -> None:
        if self.status != IngestionStatus.PROCESSING:
            raise ValueError(
                f"Cannot transition to EXTRACTED from status '{self.status.value}'. Must be PROCESSING."
            )

        self.status = IngestionStatus.EXTRACTED
        self.current_stage = "extraction_completed"
        if metrics:
            self.metrics.update(metrics)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_stage_completed",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "stage": "extracted",
                    "metrics": self.metrics,
                },
            )
        )

    def progress_to_chunked(self, metrics: dict[str, Any] | None = None) -> None:
        if self.status != IngestionStatus.EXTRACTED:
            raise ValueError(
                f"Cannot transition to CHUNKED from status '{self.status.value}'. Must be EXTRACTED."
            )

        self.status = IngestionStatus.CHUNKED
        self.current_stage = "chunking_completed"
        if metrics:
            self.metrics.update(metrics)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_stage_completed",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "stage": "chunked",
                    "metrics": self.metrics,
                },
            )
        )

    def progress_to_indexed(self, metrics: dict[str, Any] | None = None) -> None:
        if self.status != IngestionStatus.CHUNKED:
            raise ValueError(
                f"Cannot transition to INDEXED from status '{self.status.value}'. Must be CHUNKED."
            )

        self.status = IngestionStatus.INDEXED
        self.current_stage = "indexing_completed"
        if metrics:
            self.metrics.update(metrics)
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.ingestion_job_stage_completed",
                payload={
                    "job_id": self.id,
                    "asset_id": self.asset_id,
                    "stage": "indexed",
                    "metrics": self.metrics,
                },
            )
        )

    def complete(self, metrics: dict[str, Any] | None = None) -> None:
        if self.status != IngestionStatus.INDEXED:
            raise ValueError(
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
                    "metrics": self.metrics,
                },
            )
        )

    def fail(
        self,
        error_code: str,
        error_message: str,
        is_retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.status == IngestionStatus.READY:
            raise ValueError("Cannot fail a job that is already READY (terminal).")

        now = datetime.now(timezone.utc)
        self.status = IngestionStatus.FAILED
        self.error_code = error_code.strip()
        self.error_message = error_message.strip()
        self.is_retryable = is_retryable
        self.error_details = dict(details) if details is not None else {}

        attempt_record = {
            "attempt": self.attempt_count,
            "stage_at_failure": self.current_stage,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "is_retryable": self.is_retryable,
            "failed_at": now.isoformat(),
        }
        self.attempt_history.append(attempt_record)
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
        if self.status != IngestionStatus.FAILED:
            raise ValueError(
                f"Cannot schedule retry for job in status '{self.status.value}'. Must be FAILED."
            )
        if not self.is_retryable:
            raise ValueError("Cannot retry a non-retryable failure.")
        if self.attempt_count >= self.max_attempts:
            raise ValueError(
                f"Maximum attempts ({self.max_attempts}) exceeded. Terminal failure."
            )

        self.attempt_count += 1
        now = datetime.now(timezone.utc)
        self.next_retry_at = now + timedelta(seconds=delay_seconds)
        self.status = IngestionStatus.QUEUED
        self.current_stage = f"retry_attempt_{self.attempt_count}"
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

    def is_stale_callback(
        self,
        run_number: int | None = None,
        attempt_count: int | None = None,
        external_task_id: str | None = None,
    ) -> bool:
        """Determines if an incoming callback belongs to a stale / superseded attempt or run."""
        if run_number is not None and run_number < self.run_number:
            return True
        if attempt_count is not None and attempt_count < self.attempt_count:
            return True
        if (
            external_task_id is not None
            and self.external_task_id is not None
            and external_task_id != self.external_task_id
        ):
            return True
        return False

    def is_event_processed(self, event_id: str) -> bool:
        return event_id in self.processed_event_ids

    def record_event_processed(self, event_id: str) -> None:
        if event_id not in self.processed_event_ids:
            self.processed_event_ids.append(event_id)
        self.last_callback_at = datetime.now(timezone.utc)
        self.touch()

    def create_reprocess_run(
        self, created_by: str, correlation_id: str | None = None
    ) -> ContentIngestionJob:
        if self.status not in (IngestionStatus.READY, IngestionStatus.FAILED):
            raise ValueError(
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

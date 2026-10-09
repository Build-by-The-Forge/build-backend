from uuid import UUID

import pytest
from app.domain.content.enums import IngestionStatus
from app.domain.content.job import ContentIngestionJob


def test_job_creation_and_full_linear_lifecycle() -> None:
    job = ContentIngestionJob.create(
        asset_id="cass-1234",
        source_id="csrc-5678",
        tenant_id="tenant-futa",
        created_by="usr-lecturer",
        max_attempts=3,
        correlation_id="corr-1",
    )

    assert str(UUID(job.id)) == job.id and UUID(job.id).version == 4  # fits VARCHAR(36)
    assert job.asset_id == "cass-1234"
    assert job.source_id == "csrc-5678"
    assert job.tenant_id == "tenant-futa"
    assert job.status == IngestionStatus.UPLOADED
    assert job.run_number == 1
    assert job.attempt_count == 1
    assert job.max_attempts == 3

    events = job.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.ingestion_job_created"

    # 1. Queue job
    job.queue()
    assert job.status == IngestionStatus.QUEUED
    events = job.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.ingestion_job_queued"

    # 2. Start processing
    job.start(stage="parsing")
    assert job.status == IngestionStatus.PROCESSING
    assert job.current_stage == "parsing"
    assert job.started_at is not None
    events = job.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "content.ingestion_job_started"

    # 3. Extracted
    job.progress_to_extracted(metrics={"pages": 12, "ocr_used": False})
    assert job.status == IngestionStatus.EXTRACTED
    assert job.metrics["pages"] == 12

    # 4. Chunked
    job.progress_to_chunked(metrics={"chunks_count": 48})
    assert job.status == IngestionStatus.CHUNKED
    assert job.metrics["chunks_count"] == 48

    # 5. Indexed
    job.progress_to_indexed(metrics={"vectors_indexed": 48})
    assert job.status == IngestionStatus.INDEXED

    # 6. Complete
    job.complete(metrics={"total_duration_ms": 1250})
    assert job.status == IngestionStatus.READY
    assert job.completed_at is not None
    events = job.pull_events()
    assert len(events) == 4  # extracted, chunked, indexed, completed
    assert events[-1].event_type == "content.ingestion_job_completed"


def test_job_illegal_transitions() -> None:
    job = ContentIngestionJob.create(
        asset_id="cass-1",
        source_id="csrc-1",
        created_by="user",
    )

    # Cannot start from UPLOADED
    with pytest.raises(ValueError, match="Must be QUEUED"):
        job.start()

    # Queue then start
    job.queue()
    job.start()

    # Cannot skip from PROCESSING straight to INDEXED
    with pytest.raises(ValueError, match="Must be CHUNKED"):
        job.progress_to_indexed()

    # Progress to completion
    job.progress_to_extracted()
    job.progress_to_chunked()
    job.progress_to_indexed()
    job.complete()

    # Cannot fail once READY
    with pytest.raises(ValueError, match="already READY"):
        job.fail("ERR", "Should not fail ready job")


def test_job_failure_and_retry_lifecycle() -> None:
    job = ContentIngestionJob.create(
        asset_id="cass-1",
        source_id="csrc-1",
        created_by="user",
        max_attempts=3,
    )
    job.queue()
    job.start()

    # Transient AI Gateway timeout failure
    job.fail(
        error_code="AI_GATEWAY_TIMEOUT",
        error_message="Gateway timed out after 30s",
        is_retryable=True,
        details={"http_status": 504},
    )
    assert job.status == IngestionStatus.FAILED
    assert job.is_retryable is True
    assert len(job.attempt_history) == 1
    assert job.attempt_history[0]["error_code"] == "AI_GATEWAY_TIMEOUT"

    # Schedule retry #1
    job.schedule_retry(delay_seconds=10)
    assert job.status == IngestionStatus.QUEUED
    assert job.attempt_count == 2
    assert job.next_retry_at is not None

    # Start attempt #2 and fail again
    job.start()
    job.fail(
        error_code="AI_GATEWAY_TIMEOUT",
        error_message="Gateway timed out again",
        is_retryable=True,
    )
    assert job.attempt_count == 2
    assert len(job.attempt_history) == 2

    # Schedule retry #2
    job.schedule_retry(delay_seconds=10)
    assert job.attempt_count == 3
    assert job.status == IngestionStatus.QUEUED

    # Start attempt #3 and fail (exhausted max attempts = 3)
    job.start()
    job.fail(
        error_code="AI_GATEWAY_UNAVAILABLE",
        error_message="Persistent outage",
        is_retryable=True,
    )
    assert job.attempt_count == 3
    assert len(job.attempt_history) == 3

    # Attempting to schedule another retry exceeds max attempts
    with pytest.raises(ValueError, match="Maximum attempts .* exceeded"):
        job.schedule_retry()


def test_job_reprocess_run_creation() -> None:
    job = ContentIngestionJob.create(
        asset_id="cass-1",
        source_id="csrc-1",
        tenant_id="t1",
        created_by="user",
    )
    job.queue()
    job.start()
    job.progress_to_extracted()
    job.progress_to_chunked()
    job.progress_to_indexed()
    job.complete()

    # Spawning reprocess run creates run #2 in QUEUED status
    reprocess_job = job.create_reprocess_run(created_by="user-admin")
    assert reprocess_job.asset_id == "cass-1"
    assert reprocess_job.source_id == "csrc-1"
    assert reprocess_job.tenant_id == "t1"
    assert reprocess_job.run_number == 2
    assert reprocess_job.status == IngestionStatus.QUEUED
    assert reprocess_job.attempt_count == 1
    assert reprocess_job.id != job.id

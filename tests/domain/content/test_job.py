"""The ingestion job state machine (M3-08)."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.domain.content.enums import IngestionStatus
from app.domain.content.job import (
    CallbackOutcome,
    ContentIngestionJob,
    InvalidJobTransition,
    InvalidStageEvidence,
    RetryNotDue,
)

EXTRACTED = {"characters": 1200, "pages": 3, "method": "native_text"}
CHUNKED = {"chunks": 12}
INDEXED = {"indexed_chunks": 12, "index": "pgvector"}


def new_job(**kwargs) -> ContentIngestionJob:
    return ContentIngestionJob.create(
        asset_id="asset-1",
        source_id="source-1",
        tenant_id="tenant-1",
        created_by="usr-1",
        **kwargs,
    )


def dispatched(task: str = "task-1", **kwargs) -> ContentIngestionJob:
    job = new_job(**kwargs)
    job.queue()
    job.record_dispatch(task)
    return job


def event(job: ContentIngestionJob, event_type: str, stage: str | None = None, **kwargs):
    identity = {
        "run_number": job.run_number,
        "attempt_count": job.attempt_count,
        "external_task_id": job.external_task_id or "none",
    }
    identity.update(kwargs.pop("identity", {}))
    return job.apply_callback(event_type=event_type, stage=stage, **identity, **kwargs)


def to_status(job: ContentIngestionJob, status: IngestionStatus) -> None:
    steps = [
        ("extracted", EXTRACTED, IngestionStatus.EXTRACTED),
        ("chunked", CHUNKED, IngestionStatus.CHUNKED),
        ("indexed", INDEXED, IngestionStatus.INDEXED),
    ]
    for stage, metrics, reached in steps:
        if job.status == status:
            return
        assert event(job, "stage_progress", stage, metrics=metrics) is CallbackOutcome.APPLIED
        assert job.status == reached
    if status == IngestionStatus.READY:
        assert event(job, "job_completed") is CallbackOutcome.APPLIED


# --- creation and business operations ----------------------------------------------


def test_creation():
    job = new_job(max_attempts=3, correlation_id="corr-1")
    assert str(UUID(job.id)) == job.id and UUID(job.id).version == 4  # fits VARCHAR(36)
    assert (job.status, job.run_number, job.attempt_count) == (IngestionStatus.UPLOADED, 1, 1)
    assert [e.event_type for e in job.pull_events()] == ["content.ingestion_job_created"]


def test_queue_is_only_from_uploaded():
    job = new_job()
    job.queue()
    job.queue()  # idempotent
    assert job.status == IngestionStatus.QUEUED
    failed = dispatched()
    failed.fail_processing("X", "x", is_retryable=True)
    with pytest.raises(InvalidJobTransition):
        failed.queue()  # a failed job is requeued only through schedule_retry


def test_dispatch_moves_queued_to_processing_with_the_task_identity():
    job = dispatched("task-abc")
    assert (job.status, job.external_task_id) == (IngestionStatus.PROCESSING, "task-abc")


@pytest.mark.parametrize("status", ["uploaded", "processing", "ready", "failed"])
def test_dispatch_is_refused_unless_queued(status):
    job = new_job()
    if status != "uploaded":
        job.queue()
        job.record_dispatch("t")
    if status == "ready":
        to_status(job, IngestionStatus.READY)
    if status == "failed":
        job.fail_processing("X", "x", is_retryable=False)
    with pytest.raises(InvalidJobTransition):
        job.record_dispatch("t2")


def test_dispatch_requires_a_task_id():
    job = new_job()
    job.queue()
    with pytest.raises(InvalidJobTransition):
        job.record_dispatch("  ")


def test_dispatch_claim_blocks_manual_dispatch_and_expires_for_reclaim():
    job = new_job()
    job.queue()
    now = datetime.now(timezone.utc)
    job.dispatch_claim_token = "worker-a"
    job.dispatch_claim_expires_at = now + timedelta(seconds=30)

    with pytest.raises(InvalidJobTransition, match="active dispatch claim"):
        job.ensure_dispatchable(now=now)
    with pytest.raises(InvalidJobTransition, match="no longer owned"):
        job.ensure_dispatchable(now=now, claim_token="worker-b")

    job.ensure_dispatchable(now=now + timedelta(seconds=31))
    with pytest.raises(InvalidJobTransition, match="no longer owned"):
        job.ensure_dispatchable(now=now + timedelta(seconds=31), claim_token="worker-a")
    job.dispatch_claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    job.record_dispatch("task-1")
    assert job.dispatch_claim_token is None
    assert job.dispatch_claim_expires_at is None


@pytest.mark.parametrize("claim_age_seconds", [-1, 30])
def test_callback_adopts_a_task_while_dispatch_claim_exists(claim_age_seconds):
    job = new_job()
    job.queue()
    job.dispatch_claim_token = "worker-a"
    job.dispatch_claim_expires_at = datetime.now(timezone.utc) + timedelta(seconds=claim_age_seconds)

    result = job.apply_callback(
        event_type="stage_progress",
        stage="extracted",
        run_number=job.run_number,
        attempt_count=job.attempt_count,
        external_task_id="task-accepted-before-response",
        metrics=EXTRACTED,
    )

    assert result is CallbackOutcome.APPLIED
    assert job.status is IngestionStatus.EXTRACTED
    assert job.external_task_id == "task-accepted-before-response"
    assert job.last_dispatched_at is not None
    assert job.dispatch_claim_token is None
    assert job.dispatch_claim_expires_at is None


def test_uncertain_dispatch_defers_on_the_same_attempt_and_fails_at_the_bound():
    job = new_job()
    job.queue()
    job_id = (job.run_number, job.attempt_count)

    for count in range(1, 6):
        if job.next_retry_at is not None:
            job.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        can_retry_same_attempt = job.defer_uncertain_dispatch("AI_SERVICE_UNAVAILABLE", "uncertain")
        assert (job.run_number, job.attempt_count) == job_id
        assert job.metrics["uncertain_dispatch_count"] == count
        if count < 5:
            assert can_retry_same_attempt is True
            assert job.status == IngestionStatus.QUEUED
            assert job.next_retry_at is not None and job.next_retry_at > datetime.now(timezone.utc)
            assert job.last_dispatched_at is None
        else:
            assert can_retry_same_attempt is False
            assert job.status == IngestionStatus.FAILED
            assert job.is_retryable is True
            assert len(job.attempt_history) == 1


def test_new_retry_attempt_resets_only_its_uncertain_dispatch_counter():
    job = new_job()
    job.queue()
    job.defer_uncertain_dispatch("AI_SERVICE_UNAVAILABLE", "uncertain", max_uncertain_dispatches=1)
    job.schedule_retry(delay_seconds=0)

    assert job.attempt_count == 2
    assert job.metrics["uncertain_dispatch_attempt"] == 2
    assert job.metrics["uncertain_dispatch_count"] == 0
    assert job.last_dispatched_at is None


def test_dispatch_failure_is_only_from_queued():
    job = new_job()
    job.queue()
    job.fail_dispatch("AI_SERVICE_UNAVAILABLE", "down", is_retryable=True)
    assert (job.status, job.error_code) == (IngestionStatus.FAILED, "AI_SERVICE_UNAVAILABLE")
    with pytest.raises(InvalidJobTransition):
        dispatched().fail_dispatch("X", "x", is_retryable=True)


def test_start_no_longer_exists():
    assert not hasattr(ContentIngestionJob, "start")


# --- the full successful path --------------------------------------------------------


def test_ready_only_after_every_stage_and_completion():
    job = dispatched()
    to_status(job, IngestionStatus.READY)
    assert job.status == IngestionStatus.READY
    assert job.completed_at is not None
    assert job.metrics["chunks"] == 12 and job.metrics["indexed_chunks"] == 12


@pytest.mark.parametrize(
    "status",
    [IngestionStatus.PROCESSING, IngestionStatus.EXTRACTED, IngestionStatus.CHUNKED],
)
def test_completion_before_indexing_is_not_allowed(status):
    job = dispatched()
    to_status(job, status)
    assert event(job, "job_completed") is CallbackOutcome.NOT_ALLOWED
    assert job.status == status


# --- ordering ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        (IngestionStatus.PROCESSING, "chunked"),
        (IngestionStatus.PROCESSING, "indexed"),
        (IngestionStatus.EXTRACTED, "indexed"),
    ],
)
def test_skipped_stages_are_not_allowed(status, stage):
    job = dispatched()
    to_status(job, status)
    metrics = {"chunked": CHUNKED, "indexed": INDEXED}[stage]
    assert event(job, "stage_progress", stage, metrics=metrics) is CallbackOutcome.NOT_ALLOWED
    assert job.status == status


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        (IngestionStatus.EXTRACTED, "extracted"),
        (IngestionStatus.CHUNKED, "extracted"),
        (IngestionStatus.INDEXED, "chunked"),
        (IngestionStatus.READY, "indexed"),
    ],
)
def test_stages_already_reached_are_superseded_never_backwards(status, stage):
    job = dispatched()
    to_status(job, status)
    metrics = {"extracted": EXTRACTED, "chunked": CHUNKED, "indexed": INDEXED}[stage]
    assert event(job, "stage_progress", stage, metrics=metrics) is CallbackOutcome.SUPERSEDED
    assert job.status == status


def test_completion_after_ready_is_superseded():
    job = dispatched()
    to_status(job, IngestionStatus.READY)
    assert event(job, "job_completed") is CallbackOutcome.SUPERSEDED


# --- failure -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        IngestionStatus.PROCESSING,
        IngestionStatus.EXTRACTED,
        IngestionStatus.CHUNKED,
        IngestionStatus.INDEXED,
    ],
)
def test_failure_applies_to_any_active_status(status):
    job = dispatched()
    to_status(job, status)
    outcome = event(job, "job_failed", error_code="OCR", error_message="bad", is_retryable=True)
    assert outcome is CallbackOutcome.APPLIED
    assert (job.status, job.error_code, job.is_retryable) == (IngestionStatus.FAILED, "OCR", True)
    assert job.attempt_history[-1]["external_task_id"] == "task-1"


def test_late_failure_after_ready_is_not_allowed():
    job = dispatched()
    to_status(job, IngestionStatus.READY)
    assert event(job, "job_failed", error_code="X") is CallbackOutcome.NOT_ALLOWED
    assert job.status == IngestionStatus.READY


def test_a_second_failure_for_the_same_attempt_is_superseded():
    job = dispatched()
    event(job, "job_failed", error_code="FIRST")
    assert event(job, "job_failed", error_code="SECOND") is CallbackOutcome.SUPERSEDED
    assert job.error_code == "FIRST"
    assert len(job.attempt_history) == 1


def test_stage_events_after_failure_are_not_allowed():
    job = dispatched()
    event(job, "job_failed")
    assert event(job, "stage_progress", "extracted", metrics=EXTRACTED) is CallbackOutcome.NOT_ALLOWED
    assert event(job, "job_completed") is CallbackOutcome.NOT_ALLOWED


@pytest.mark.parametrize("status", ["uploaded", "queued"])
def test_callbacks_for_an_undispatched_job_are_stale(status):
    job = new_job()
    if status == "queued":
        job.queue()
    outcome = job.apply_callback(event_type="job_failed", run_number=1, attempt_count=1, external_task_id="task-1")
    assert outcome is CallbackOutcome.STALE
    assert job.status.value == status


# --- attempt identity ----------------------------------------------------------------


@pytest.mark.parametrize(
    "identity",
    [
        {"run_number": 2},
        {"run_number": 0},
        {"attempt_count": 2},
        {"attempt_count": 0},
        {"external_task_id": "task-other"},
    ],
)
def test_any_identity_mismatch_is_stale(identity):
    job = dispatched()
    assert event(job, "job_failed", identity=identity) is CallbackOutcome.STALE
    assert job.status == IngestionStatus.PROCESSING


def test_retry_clears_the_task_and_increments_the_attempt_once():
    job = dispatched("task-1", max_attempts=3)
    event(job, "job_failed", is_retryable=True)
    job.schedule_retry(delay_seconds=0)
    assert (job.status, job.attempt_count, job.external_task_id) == (IngestionStatus.QUEUED, 2, None)


def test_an_old_attempts_events_cannot_touch_the_retried_job():
    """The F-7 race: after a retry, events from the previous task are stale,
    whatever attempt number they carry."""
    job = dispatched("task-1", max_attempts=3)
    event(job, "job_failed", is_retryable=True)
    job.schedule_retry(delay_seconds=0)

    for attempt in (1, 2):
        old = job.apply_callback(event_type="job_failed", run_number=1, attempt_count=attempt, external_task_id="task-1")
        assert old is CallbackOutcome.STALE
    assert job.status == IngestionStatus.QUEUED

    job.record_dispatch("task-2")
    old = job.apply_callback(event_type="job_failed", run_number=1, attempt_count=2, external_task_id="task-1")
    assert old is CallbackOutcome.STALE
    assert event(job, "stage_progress", "extracted", metrics=EXTRACTED) is CallbackOutcome.APPLIED


def test_retry_rules():
    job = dispatched(max_attempts=2)
    with pytest.raises(InvalidJobTransition):
        job.schedule_retry()  # not failed
    event(job, "job_failed", is_retryable=False)
    with pytest.raises(InvalidJobTransition, match="non-retryable"):
        job.schedule_retry()

    exhausted = dispatched(max_attempts=1)
    event(exhausted, "job_failed", is_retryable=True)
    with pytest.raises(InvalidJobTransition, match="Maximum attempts"):
        exhausted.schedule_retry()


def test_a_retried_attempt_is_not_dispatched_before_its_delay():
    job = dispatched(max_attempts=3)
    event(job, "job_failed", is_retryable=True)
    job.schedule_retry(delay_seconds=60)
    with pytest.raises(RetryNotDue):
        job.record_dispatch("task-2")
    assert job.status == IngestionStatus.QUEUED
    later = datetime.now(timezone.utc) + timedelta(seconds=61)
    job.ensure_dispatchable(now=later)  # allowed once the delay has elapsed
    job.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    job.record_dispatch("task-2")
    assert (job.status, job.next_retry_at) == (IngestionStatus.PROCESSING, None)


# --- evidence ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metrics",
    [
        {},
        {"characters": 0, "pages": 1, "method": "ocr"},
        {"characters": 10, "pages": -1, "method": "ocr"},
        {"characters": 10, "pages": 1, "method": "guess"},
        {"characters": True, "pages": 1, "method": "ocr"},
        {"characters": "10", "pages": 1, "method": "ocr"},
    ],
)
def test_extraction_needs_evidence(metrics):
    job = dispatched()
    with pytest.raises(InvalidStageEvidence):
        event(job, "stage_progress", "extracted", metrics=metrics)
    assert job.status == IngestionStatus.PROCESSING


@pytest.mark.parametrize("metrics", [{}, {"chunks": 0}, {"chunks": 1.5}])
def test_chunking_needs_evidence(metrics):
    job = dispatched()
    to_status(job, IngestionStatus.EXTRACTED)
    with pytest.raises(InvalidStageEvidence):
        event(job, "stage_progress", "chunked", metrics=metrics)


@pytest.mark.parametrize(
    "metrics",
    [
        {},
        {"indexed_chunks": 11, "index": "pgvector"},  # not every chunk indexed
        {"indexed_chunks": 12},  # no durable index named
        {"indexed_chunks": 12, "index": "  "},
    ],
)
def test_indexing_needs_evidence_matching_the_chunk_count(metrics):
    job = dispatched()
    to_status(job, IngestionStatus.CHUNKED)
    with pytest.raises(InvalidStageEvidence):
        event(job, "stage_progress", "indexed", metrics=metrics)
    assert job.status == IngestionStatus.CHUNKED


def test_unknown_stage_or_event_type_is_invalid():
    job = dispatched()
    with pytest.raises(InvalidStageEvidence):
        event(job, "stage_progress", "embedded", metrics={})
    with pytest.raises(InvalidStageEvidence):
        event(job, "job_started")


# --- reprocess -----------------------------------------------------------------------


def test_reprocess_creates_a_new_run_from_terminal_states_only():
    job = dispatched()
    with pytest.raises(InvalidJobTransition):
        job.create_reprocess_run(created_by="usr-2")
    to_status(job, IngestionStatus.READY)
    run2 = job.create_reprocess_run(created_by="usr-2")
    assert (run2.run_number, run2.status, run2.attempt_count) == (2, IngestionStatus.QUEUED, 1)
    assert run2.id != job.id and job.status == IngestionStatus.READY


def test_a_retry_time_stored_without_timezone_is_read_as_utc():
    job = dispatched(max_attempts=3)
    event(job, "job_failed", is_retryable=True)
    job.schedule_retry(delay_seconds=60)
    job.next_retry_at = job.next_retry_at.replace(tzinfo=None)  # as SQLite returns it
    with pytest.raises(RetryNotDue):
        job.ensure_dispatchable()

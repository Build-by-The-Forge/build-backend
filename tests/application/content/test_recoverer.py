from datetime import datetime, timedelta, timezone

import pytest

from app.application.content.job_handlers import RecoverIngestionJobHandler
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetMimeType, IngestionStatus
from app.domain.content.gateway import AIServiceStatusResult
from app.domain.content.job import ContentIngestionJob
from tests.application.content.managed_storage import managed
from tests.application.content.test_job_handlers import FakeContentUnitOfWork

EXTRACTED = {"characters": 1200, "pages": 3, "method": "native_text"}


class StatusGateway:
    def __init__(self, status: AIServiceStatusResult | None = None, error: Exception | None = None) -> None:
        self.status = status
        self.error = error

    async def fetch_job_status(self, _task_id, _tenant_id, _correlation_id):
        if self.error is not None:
            raise self.error
        return self.status


class RetryableGatewayError(Exception):
    is_retryable = True
    error_code = "AI_SERVICE_POLL_ERROR"


async def setup_active_job():
    uow = FakeContentUnitOfWork()
    asset = ContentAsset.create(
        source_id="source-1",
        file_name="document.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=100,
        content_sha256="a" * 64,
        storage_uri="s3://bucket/object",
        created_by="usr-1",
        created_by_email="user@example.com",
        tenant_id="tenant-1",
        ingestion_status=IngestionStatus.PROCESSING,
    )
    managed(asset)
    await uow.assets.save_asset(asset)
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=asset.source_id,
        tenant_id=asset.tenant_id,
        created_by="usr-1",
    )
    job.queue()
    job.record_dispatch("task-1")
    await uow.jobs.save_job(job)
    return uow, job, asset


def task_status(job, *, state: str, events: list[dict] | None = None) -> AIServiceStatusResult:
    return AIServiceStatusResult(
        external_task_id=job.external_task_id,
        job_id=job.id,
        run_number=job.run_number,
        attempt_count=job.attempt_count,
        state=state,
        events=events or [],
    )


@pytest.mark.asyncio
async def test_live_lease_extends_deadline_without_moving_dispatch_anchor():
    uow, job, _ = await setup_active_job()
    old_dispatch_time = job.last_dispatched_at
    now = datetime.now(timezone.utc)
    stale_updated_at = now - timedelta(seconds=700)
    job.updated_at = stale_updated_at

    result = await RecoverIngestionJobHandler(uow, StatusGateway(task_status(job, state="running"))).handle(
        job,
        max_in_flight_seconds=3600,
        now=now,
    )

    assert result.action == "alive"
    assert result.job.status is IngestionStatus.PROCESSING
    assert result.job.updated_at > stale_updated_at
    assert result.job.last_dispatched_at == old_dispatch_time


@pytest.mark.asyncio
async def test_hard_cap_fails_even_when_the_ai_lease_is_live():
    uow, job, asset = await setup_active_job()
    now = datetime.now(timezone.utc)
    job.last_dispatched_at = now - timedelta(seconds=3601)

    result = await RecoverIngestionJobHandler(uow, StatusGateway(task_status(job, state="running"))).handle(
        job,
        max_in_flight_seconds=3600,
        now=now,
    )

    assert result.action == "timeout"
    assert result.job.status is IngestionStatus.FAILED
    assert (result.job.error_code, result.job.is_retryable) == ("AI_TASK_TIMEOUT", True)
    assert result.job.last_dispatched_at == now - timedelta(seconds=3601)
    assert asset.ingestion_status is IngestionStatus.FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["stalled", "failed", "completed"])
async def test_non_live_task_fails_retryably_as_lost(state):
    uow, job, asset = await setup_active_job()

    result = await RecoverIngestionJobHandler(uow, StatusGateway(task_status(job, state=state))).handle(
        job,
        max_in_flight_seconds=3600,
    )

    assert result.action == "lost"
    assert result.job.status is IngestionStatus.FAILED
    assert (result.job.error_code, result.job.is_retryable) == ("AI_TASK_LOST", True)
    assert asset.ingestion_status is IngestionStatus.FAILED


@pytest.mark.asyncio
async def test_unknown_task_is_failed_as_lost():
    uow, job, _ = await setup_active_job()
    error = RetryableGatewayError("task missing")
    error.error_code = "AI_TASK_NOT_FOUND"

    result = await RecoverIngestionJobHandler(uow, StatusGateway(error=error)).handle(
        job,
        max_in_flight_seconds=3600,
    )

    assert result.action == "lost"
    assert result.job.error_code == "AI_TASK_LOST"


@pytest.mark.asyncio
async def test_unreachable_ai_service_changes_nothing():
    uow, job, asset = await setup_active_job()
    updated_at = job.updated_at
    last_dispatched_at = job.last_dispatched_at

    result = await RecoverIngestionJobHandler(uow, StatusGateway(error=RetryableGatewayError("offline"))).handle(
        job,
        max_in_flight_seconds=3600,
    )

    assert result.action == "unreachable"
    assert result.job.status is IngestionStatus.PROCESSING
    assert result.job.updated_at == updated_at
    assert result.job.last_dispatched_at == last_dispatched_at
    assert asset.ingestion_status is IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_undelivered_events_are_applied_before_a_stalled_task_is_failed():
    uow, job, asset = await setup_active_job()
    event = {
        "event_id": "event-extracted",
        "job_id": job.id,
        "external_task_id": job.external_task_id,
        "run_number": job.run_number,
        "attempt_count": job.attempt_count,
        "event_type": "stage_progress",
        "stage": "extracted",
        "metrics": EXTRACTED,
    }

    result = await RecoverIngestionJobHandler(
        uow,
        StatusGateway(task_status(job, state="stalled", events=[event])),
    ).handle(job, max_in_flight_seconds=3600)

    assert result.callback_outcomes == [("event-extracted", "applied")]
    assert result.action == "lost"
    assert result.job.status is IngestionStatus.FAILED
    assert result.job.attempt_history[-1]["stage_at_failure"] == "extraction_completed"
    assert asset.ingestion_status is IngestionStatus.FAILED
    assert "event-extracted" in uow.ingestion_events.records

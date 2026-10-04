from datetime import datetime, timezone
import pytest

from app.application.content.job_commands import (
    CreateIngestionJobCommand,
    DispatchIngestionJobCommand,
    HandleAICallbackCommand,
)
from app.application.content.job_handlers import (
    CreateIngestionJobHandler,
    DispatchIngestionJobHandler,
    HandleAICallbackHandler,
)
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AuthorityLevel,
    ContentSourceType,
    IngestionStatus,
    VisibilityScope,
)
from app.domain.content.gateway import AIServiceDispatchResult
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.events.event_bus import EventBus
from tests.application.content.test_job_handlers import FakeContentUnitOfWork


class FakeAIGateway:
    def __init__(self) -> None:
        self.dispatched_jobs: list[str] = []

    async def dispatch_ingestion_job(
        self, job, asset, source, callback_url
    ) -> AIServiceDispatchResult:
        self.dispatched_jobs.append(job.id)
        return AIServiceDispatchResult(
            external_task_id=f"aitask-{job.id}",
            accepted_at=datetime.now(timezone.utc),
            status="accepted",
        )


@pytest.mark.asyncio
async def test_dispatch_ingestion_handler() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    gateway = FakeAIGateway()

    source = ContentSource.create(
        code="CS_SRC_DISP",
        name="Source",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.sources.save_source(source)

    asset = ContentAsset.create(
        source_id=source.id,
        file_name="slides.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=2048,
        content_sha256="c" * 64,
        storage_uri="s3://build/slides.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)

    # 1. Create job
    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(
        CreateIngestionJobCommand(asset_id=asset.id, created_by="usr-1")
    )
    assert job.status == IngestionStatus.QUEUED

    # 2. Dispatch job
    dispatch_handler = DispatchIngestionJobHandler(uow, gateway, bus)
    dispatched_job = await dispatch_handler.handle(
        DispatchIngestionJobCommand(job_id=job.id, callback_url="/cb")
    )

    assert dispatched_job.status == IngestionStatus.PROCESSING
    assert dispatched_job.current_stage == "dispatched_to_ai"
    assert dispatched_job.external_task_id == f"aitask-{job.id}"
    assert len(gateway.dispatched_jobs) == 1
    assert asset.ingestion_status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_ai_callback_pipeline_progression_and_idempotency() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    gateway = FakeAIGateway()

    source = ContentSource.create(
        code="CS_SRC_CB",
        name="Source CB",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.sources.save_source(source)

    asset = ContentAsset.create(
        source_id=source.id,
        file_name="doc.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="d" * 64,
        storage_uri="s3://build/doc.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)

    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(
        CreateIngestionJobCommand(asset_id=asset.id, created_by="usr-1")
    )
    await DispatchIngestionJobHandler(uow, gateway, bus).handle(
        DispatchIngestionJobCommand(job_id=job.id)
    )

    callback_handler = HandleAICallbackHandler(uow, bus)

    # 1. First callback: EXTRACTED
    job_res, already_proc = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            event_id="evt-1",
            event_type="stage_progress",
            stage="extracted",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"pages": 10},
        )
    )
    assert already_proc is False
    assert job_res.status == IngestionStatus.EXTRACTED
    assert asset.ingestion_status == IngestionStatus.EXTRACTED

    # 2. Duplicate callback with same event_id: returns already_processed=True without error
    job_dup, is_dup = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            event_id="evt-1",
            event_type="stage_progress",
            stage="extracted",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
        )
    )
    assert is_dup is True
    assert job_dup.status == IngestionStatus.EXTRACTED

    # 3. Next stage: CHUNKED
    job_res, _ = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            event_id="evt-2",
            event_type="stage_progress",
            stage="chunked",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"chunks": 40},
        )
    )
    assert job_res.status == IngestionStatus.CHUNKED

    # 4. Next stage: INDEXED
    job_res, _ = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            event_id="evt-3",
            event_type="stage_progress",
            stage="indexed",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"indexed": 40},
        )
    )
    assert job_res.status == IngestionStatus.INDEXED

    # 5. Complete
    job_res, _ = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            event_id="evt-4",
            event_type="job_completed",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"duration_ms": 1500},
        )
    )
    assert job_res.status == IngestionStatus.READY
    assert asset.ingestion_status == IngestionStatus.READY


@pytest.mark.asyncio
async def test_stale_attempt_protection() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()

    source = ContentSource.create(
        code="CS_STALE_SRC",
        name="Source Stale",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.sources.save_source(source)

    asset = ContentAsset.create(
        source_id=source.id,
        file_name="stale.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="e" * 64,
        storage_uri="s3://build/stale.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)

    # Create Job and retry it -> attempt_count becomes 2
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        created_by="usr-1",
    )
    job.queue()
    job.start()
    job.fail(error_code="TIMEOUT", error_message="Timeout on attempt 1", is_retryable=True)
    job.schedule_retry(delay_seconds=10)
    job.record_dispatch(external_task_id="aitask-attempt-2")
    await uow.jobs.save_job(job)

    assert job.attempt_count == 2
    assert job.external_task_id == "aitask-attempt-2"

    callback_handler = HandleAICallbackHandler(uow, bus)

    # Delayed Attempt-1 callback arrives after Attempt-2 has started
    job_res, is_stale = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            event_id="evt-delayed-attempt-1",
            event_type="stage_progress",
            stage="extracted",
            external_task_id="aitask-attempt-1",  # mismatching old task ID
            run_number=1,
            attempt_count=1,  # older attempt
        )
    )

    # Stale callback must be safely ignored
    assert is_stale is True
    assert job_res.attempt_count == 2
    assert job_res.external_task_id == "aitask-attempt-2"
    assert job_res.status == IngestionStatus.PROCESSING

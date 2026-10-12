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
from app.domain.content.gateway import AIServiceDispatchResult, IngestionDispatchActor
from app.domain.content.job import CallbackOutcome, ContentIngestionJob
from app.domain.content.source import ContentSource
from app.events.event_bus import EventBus
from tests.application.content.test_job_handlers import FakeContentUnitOfWork


def dispatch_cmd(job_id: str, tenant_id: str = "tenant-1") -> DispatchIngestionJobCommand:
    return DispatchIngestionJobCommand(
        job_id=job_id,
        tenant_id=tenant_id,
        user_id="usr-1",
        membership_id="mem-1",
        role="lecturer",
        permission="content.job.manage",
    )


class FakeAIGateway:
    def __init__(self, error: Exception | None = None) -> None:
        self.dispatched_jobs: list[str] = []
        self.actors: list[IngestionDispatchActor] = []
        self.error = error

    async def dispatch_ingestion_job(self, job, asset, source, actor) -> AIServiceDispatchResult:
        self.dispatched_jobs.append(job.id)
        self.actors.append(actor)
        if self.error is not None:
            raise self.error
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
        tenant_id="tenant-1",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)

    # 1. Create job
    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(CreateIngestionJobCommand(asset_id=asset.id, tenant_id="tenant-1", created_by="usr-1"))
    assert job.status == IngestionStatus.QUEUED

    # 2. Dispatch job
    dispatch_handler = DispatchIngestionJobHandler(uow, gateway, bus)
    dispatched_job = await dispatch_handler.handle(dispatch_cmd(job.id))

    assert dispatched_job.status == IngestionStatus.PROCESSING
    assert dispatched_job.current_stage == "dispatched_to_ai"
    assert dispatched_job.external_task_id == f"aitask-{job.id}"
    assert len(gateway.dispatched_jobs) == 1
    # The signed context will name the job's tenant, the caller and the one
    # checked permission; no callback destination is passed at all.
    assert gateway.actors == [
        IngestionDispatchActor(
            tenant_id="tenant-1",
            user_id="usr-1",
            membership_id="mem-1",
            role="lecturer",
            permission="content.job.manage",
        )
    ]
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
        tenant_id="tenant-1",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)

    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(CreateIngestionJobCommand(asset_id=asset.id, tenant_id="tenant-1", created_by="usr-1"))
    await DispatchIngestionJobHandler(uow, gateway, bus).handle(dispatch_cmd(job.id))

    callback_handler = HandleAICallbackHandler(uow, bus)

    # 1. First callback: EXTRACTED
    job_res, already_proc = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            tenant_id="tenant-1",
            event_id="evt-1",
            event_type="stage_progress",
            stage="extracted",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"characters": 5000, "pages": 10, "method": "native_text"},
        )
    )
    assert already_proc is CallbackOutcome.APPLIED
    assert job_res.status == IngestionStatus.EXTRACTED
    assert asset.ingestion_status == IngestionStatus.EXTRACTED

    # 2. The identical event delivered again is an idempotent duplicate
    job_dup, is_dup = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            tenant_id="tenant-1",
            event_id="evt-1",
            event_type="stage_progress",
            stage="extracted",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"characters": 5000, "pages": 10, "method": "native_text"},
        )
    )
    assert is_dup is CallbackOutcome.DUPLICATE
    assert job_dup.status == IngestionStatus.EXTRACTED

    # 3. Next stage: CHUNKED
    job_res, _ = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            tenant_id="tenant-1",
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
            tenant_id="tenant-1",
            event_id="evt-3",
            event_type="stage_progress",
            stage="indexed",
            external_task_id=job.external_task_id,
            run_number=1,
            attempt_count=1,
            metrics={"indexed_chunks": 40, "index": "pgvector"},
        )
    )
    assert job_res.status == IngestionStatus.INDEXED

    # 5. Complete
    job_res, _ = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            tenant_id="tenant-1",
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
        tenant_id="tenant-1",
        created_by="usr-1",
    )
    job.queue()
    job.record_dispatch(external_task_id="aitask-attempt-1")
    job.fail_processing(error_code="TIMEOUT", error_message="Timeout on attempt 1", is_retryable=True)
    job.schedule_retry(delay_seconds=0)
    job.record_dispatch(external_task_id="aitask-attempt-2")
    await uow.jobs.save_job(job)

    assert job.attempt_count == 2
    assert job.external_task_id == "aitask-attempt-2"

    callback_handler = HandleAICallbackHandler(uow, bus)

    # Delayed Attempt-1 callback arrives after Attempt-2 has started
    job_res, is_stale = await callback_handler.handle(
        HandleAICallbackCommand(
            job_id=job.id,
            tenant_id="tenant-1",
            event_id="evt-delayed-attempt-1",
            event_type="stage_progress",
            stage="extracted",
            external_task_id="aitask-attempt-1",  # mismatching old task ID
            run_number=1,
            attempt_count=1,  # older attempt
        )
    )

    # Stale callback must be safely ignored
    assert is_stale is CallbackOutcome.STALE
    assert job_res.attempt_count == 2
    assert job_res.external_task_id == "aitask-attempt-2"
    assert job_res.status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
@pytest.mark.parametrize("job_tenant", ["tenant-2", None])
async def test_dispatch_of_another_tenants_or_platform_job_is_refused(job_tenant) -> None:
    uow, bus, gateway = FakeContentUnitOfWork(), EventBus(), FakeAIGateway()
    job = ContentIngestionJob.create(asset_id="asset-x", source_id="src-x", tenant_id=job_tenant, created_by="usr-1")
    job.queue()
    await uow.jobs.save_job(job)

    with pytest.raises(ValueError, match="does not exist"):
        await DispatchIngestionJobHandler(uow, gateway, bus).handle(dispatch_cmd(job.id))

    assert gateway.dispatched_jobs == []
    assert job.status == IngestionStatus.QUEUED


@pytest.mark.asyncio
@pytest.mark.parametrize("retryable", [True, False])
async def test_failed_dispatch_is_recorded_not_raised(retryable) -> None:
    """queued -> failed is a business outcome the unit of work must commit."""
    from app.infrastructure.content.ai_gateway import AIServiceGatewayError

    uow, bus = FakeContentUnitOfWork(), EventBus()
    error = AIServiceGatewayError("AI down", error_code="AI_SERVICE_UNAVAILABLE", is_retryable=retryable)
    gateway = FakeAIGateway(error=error)
    asset = ContentAsset.create(
        source_id="src-x",
        file_name="x.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=10,
        content_sha256="f" * 64,
        storage_uri="s3://build/x.pdf",
        tenant_id="tenant-1",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)
    source = ContentSource.create(
        code="SRC_X",
        name="X",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.sources.save_source(source)
    job = ContentIngestionJob.create(asset_id=asset.id, source_id=source.id, tenant_id="tenant-1", created_by="usr-1")
    job.queue()
    await uow.jobs.save_job(job)

    result = await DispatchIngestionJobHandler(uow, gateway, bus).handle(dispatch_cmd(job.id))

    assert result.status == IngestionStatus.FAILED
    assert (result.error_code, result.is_retryable) == ("AI_SERVICE_UNAVAILABLE", retryable)
    assert uow.jobs.jobs[job.id].status == IngestionStatus.FAILED
    assert asset.ingestion_status == IngestionStatus.FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize("job_tenant", ["tenant-2", None])
async def test_callback_for_another_tenants_or_platform_job_changes_nothing(job_tenant) -> None:
    """A signed callback for tenant-1 cannot touch a job it does not own (B.3 step 3)."""
    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = ContentIngestionJob.create(asset_id="asset-x", source_id="src-x", tenant_id=job_tenant, created_by="usr-1")
    job.queue()
    job.record_dispatch(external_task_id="task-x")
    await uow.jobs.save_job(job)

    result, processed = await HandleAICallbackHandler(uow, bus).handle(
        HandleAICallbackCommand(
            job_id=job.id,
            tenant_id="tenant-1",
            event_id="evt-cross",
            event_type="job_failed",
            external_task_id="task-x",
            run_number=1,
            attempt_count=1,
        )
    )

    assert (result, processed) == (None, None)
    assert job.status == IngestionStatus.PROCESSING
    assert uow.ingestion_events.records == {}


# --- M3-08: outcomes through the handler -----------------------------------------------

EXTRACTED_EVIDENCE = {"characters": 900, "pages": 2, "method": "native_text"}


async def _dispatched_job(uow, task="task-1", max_attempts=3):
    job = ContentIngestionJob.create(
        asset_id="asset-m308",
        source_id="src-m308",
        tenant_id="tenant-1",
        created_by="usr-1",
        max_attempts=max_attempts,
    )
    job.queue()
    job.record_dispatch(external_task_id=task)
    await uow.jobs.save_job(job)
    return job


def _cb(job, event_id, event_type, stage=None, task=None, attempt=None, **kwargs):
    return HandleAICallbackCommand(
        job_id=job.id,
        tenant_id="tenant-1",
        event_id=event_id,
        event_type=event_type,
        stage=stage,
        external_task_id=task or job.external_task_id,
        run_number=job.run_number,
        attempt_count=attempt or job.attempt_count,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_an_event_that_is_not_allowed_yet_is_not_consumed() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = await _dispatched_job(uow)
    handler = HandleAICallbackHandler(uow, bus)

    early, outcome = await handler.handle(_cb(job, "evt-done", "job_completed"))
    assert outcome is CallbackOutcome.NOT_ALLOWED
    assert "evt-done" not in uow.ingestion_events.records
    assert early.status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_missing_evidence_changes_and_consumes_nothing() -> None:
    from app.domain.content.job import InvalidStageEvidence

    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = await _dispatched_job(uow)
    with pytest.raises(InvalidStageEvidence):
        await HandleAICallbackHandler(uow, bus).handle(_cb(job, "evt-x", "stage_progress", "extracted", metrics={"pages": 2}))
    assert job.status == IngestionStatus.PROCESSING
    assert uow.ingestion_events.records == {}


@pytest.mark.asyncio
async def test_an_old_task_cannot_fail_the_retried_attempt() -> None:
    """Audit F-7: before M3-08 the old task's own retry (attempt 2) matched the
    retried job and could fail it while queued."""
    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = await _dispatched_job(uow, task="task-1")
    handler = HandleAICallbackHandler(uow, bus)
    await handler.handle(_cb(job, "evt-f1", "job_failed", is_retryable=True))
    job.schedule_retry(delay_seconds=0)

    _, outcome = await handler.handle(_cb(job, "evt-old", "job_failed", task="task-1", attempt=2))
    assert outcome is CallbackOutcome.STALE
    assert job.status == IngestionStatus.QUEUED


@pytest.mark.asyncio
async def test_a_retried_job_is_not_dispatched_before_its_delay() -> None:
    from app.domain.content.job import RetryNotDue

    uow, bus, gateway = FakeContentUnitOfWork(), EventBus(), FakeAIGateway()
    source = ContentSource.create(
        code="SRC_DELAY",
        name="Delay",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.sources.save_source(source)
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="d.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=10,
        content_sha256="d" * 64,
        storage_uri="s3://build/d.pdf",
        tenant_id="tenant-1",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await uow.assets.save_asset(asset)
    job = ContentIngestionJob.create(asset_id=asset.id, source_id=source.id, tenant_id="tenant-1", created_by="usr-1")
    job.queue()
    job.record_dispatch("task-1")
    job.fail_processing("TIMEOUT", "t", is_retryable=True)
    job.schedule_retry(delay_seconds=300)
    await uow.jobs.save_job(job)

    with pytest.raises(RetryNotDue):
        await DispatchIngestionJobHandler(uow, gateway, bus).handle(dispatch_cmd(job.id))
    assert gateway.dispatched_jobs == []
    assert job.status == IngestionStatus.QUEUED


# --- M3-08: the event ledger -----------------------------------------------------------


class RecordingSecurityEvents:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    async def record(self, event, *, user_id=None, metadata=None) -> None:
        self.events.append((event, metadata))


@pytest.mark.asyncio
async def test_same_event_id_with_different_content_is_a_conflict() -> None:
    from app.application.identity.ports.security_events import SecurityEvent

    uow, bus, security = FakeContentUnitOfWork(), EventBus(), RecordingSecurityEvents()
    job = await _dispatched_job(uow)
    handler = HandleAICallbackHandler(uow, bus, security)

    first = _cb(job, "evt-1", "stage_progress", "extracted", metrics=EXTRACTED_EVIDENCE)
    assert (await handler.handle(first))[1] is CallbackOutcome.APPLIED
    assert (await handler.handle(first))[1] is CallbackOutcome.DUPLICATE

    forged = _cb(job, "evt-1", "stage_progress", "extracted", metrics={**EXTRACTED_EVIDENCE, "pages": 99})
    assert (await handler.handle(forged))[1] is CallbackOutcome.CONFLICT
    assert job.metrics["pages"] == 2
    assert [e for e, _ in security.events] == [SecurityEvent.AI_CALLBACK_EVENT_CONFLICT]
    assert security.events[0][1]["event_id"] == "evt-1"


@pytest.mark.asyncio
async def test_an_event_id_recorded_for_another_job_is_a_conflict() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    job_a = await _dispatched_job(uow, task="task-a")
    job_b = await _dispatched_job(uow, task="task-b")
    handler = HandleAICallbackHandler(uow, bus)
    await handler.handle(_cb(job_a, "evt-shared", "job_failed"))
    _, outcome = await handler.handle(_cb(job_b, "evt-shared", "job_failed"))
    assert outcome is CallbackOutcome.CONFLICT
    assert job_b.status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_a_legacy_event_id_is_never_treated_as_a_verified_duplicate() -> None:
    from datetime import datetime, timezone

    from app.domain.content.ingestion_event import IngestionEventRecord

    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = await _dispatched_job(uow)
    await uow.ingestion_events.add(
        IngestionEventRecord(
            event_id="evt-old",
            job_id=job.id,
            tenant_id="tenant-1",
            run_number=None,
            attempt_count=None,
            external_task_id=None,
            event_type=None,
            stage=None,
            payload_sha256=None,
            outcome=CallbackOutcome.LEGACY,
            received_at=datetime.now(timezone.utc),
        )
    )
    _, outcome = await HandleAICallbackHandler(uow, bus).handle(_cb(job, "evt-old", "job_failed"))
    assert outcome is CallbackOutcome.LEGACY
    assert job.status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_outcomes_are_recorded_except_not_allowed() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = await _dispatched_job(uow)
    handler = HandleAICallbackHandler(uow, bus)
    await handler.handle(_cb(job, "evt-stale", "job_failed", task="task-old"))
    await handler.handle(_cb(job, "evt-early", "job_completed"))
    await handler.handle(_cb(job, "evt-x1", "stage_progress", "extracted", metrics=EXTRACTED_EVIDENCE))
    await handler.handle(_cb(job, "evt-x2", "stage_progress", "extracted", metrics=EXTRACTED_EVIDENCE))
    outcomes = {k: r.outcome for k, r in uow.ingestion_events.records.items()}
    assert outcomes == {
        "evt-stale": CallbackOutcome.STALE,
        "evt-x1": CallbackOutcome.APPLIED,
        "evt-x2": CallbackOutcome.SUPERSEDED,
    }
    assert all(len(r.payload_sha256 or "") == 64 for r in uow.ingestion_events.records.values())


def test_the_digest_ignores_key_order_but_not_meaning() -> None:
    from app.domain.content.ingestion_event import canonical_event_digest

    base = dict(
        job_id="j",
        event_type="stage_progress",
        run_number=1,
        attempt_count=1,
        external_task_id="t",
        stage="extracted",
        error_code=None,
        error_message=None,
        is_retryable=False,
        details={},
    )
    a = canonical_event_digest(metrics={"pages": 1, "characters": 5, "method": "ocr"}, **base)
    b = canonical_event_digest(metrics={"method": "ocr", "characters": 5, "pages": 1}, **base)
    c = canonical_event_digest(metrics={"method": "ocr", "characters": 5, "pages": 2}, **base)
    d = canonical_event_digest(metrics={"pages": 1, "characters": 5, "method": "ocr"}, **{**base, "attempt_count": 2})
    assert a == b
    assert len({a, c, d}) == 3


# --- M3-09: reconcile ----------------------------------------------------------------------


class StatusGateway:
    def __init__(self, status=None, error=None) -> None:
        self.status, self.error = status, error
        self.calls: list[tuple] = []

    async def fetch_job_status(self, external_task_id, tenant_id, correlation_id):
        self.calls.append((external_task_id, tenant_id, correlation_id))
        if self.error is not None:
            raise self.error
        return self.status


def _status(job, events, **overrides):
    from app.domain.content.gateway import AIServiceStatusResult

    fields = dict(
        external_task_id=job.external_task_id,
        job_id=job.id,
        run_number=job.run_number,
        attempt_count=job.attempt_count,
        state="failed",
        events=events,
    )
    fields.update(overrides)
    return AIServiceStatusResult(**fields)


def _body(job, event_id, event_type, **fields):
    return {
        "event_id": event_id,
        "job_id": job.id,
        "external_task_id": job.external_task_id,
        "run_number": job.run_number,
        "attempt_count": job.attempt_count,
        "event_type": event_type,
        **fields,
    }


def _reconcile(uow, gateway, tenant_id="tenant-1", job_id=None):
    from app.application.content.job_commands import ReconcileIngestionJobCommand
    from app.application.content.job_handlers import ReconcileIngestionJobHandler

    return ReconcileIngestionJobHandler(uow, gateway, EventBus()).handle(
        ReconcileIngestionJobCommand(job_id=job_id, tenant_id=tenant_id)
    )


@pytest.mark.asyncio
async def test_reconcile_applies_undelivered_events_and_skips_applied_ones() -> None:
    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow, task="task-r")
    extracted = _body(job, "evt-1", "stage_progress", stage="extracted", metrics=EXTRACTED_EVIDENCE)
    # evt-1 was delivered as a callback; evt-2 never arrived.
    await HandleAICallbackHandler(uow, EventBus()).handle(
        _cb(job, "evt-1", "stage_progress", "extracted", metrics=EXTRACTED_EVIDENCE)
    )
    failed = _body(job, "evt-2", "job_failed", error_code="X", error_message="x", is_retryable=True)
    gateway = StatusGateway(_status(job, [extracted, failed]))

    result = await _reconcile(uow, gateway, job_id=job.id)

    assert result.outcomes == [("evt-1", "duplicate"), ("evt-2", "applied")]
    assert (result.job.status, result.job.error_code) == (IngestionStatus.FAILED, "X")
    assert gateway.calls == [("task-r", "tenant-1", job.id)]
    # The job is now terminal: there is nothing left to reconcile.
    from app.domain.content.job import InvalidJobTransition

    with pytest.raises(InvalidJobTransition):
        await _reconcile(uow, gateway, job_id=job.id)


@pytest.mark.asyncio
async def test_reconciling_twice_while_active_is_idempotent() -> None:
    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow)
    extracted = _body(job, "evt-1", "stage_progress", stage="extracted", metrics=EXTRACTED_EVIDENCE)
    gateway = StatusGateway(_status(job, [extracted], state="running"))
    first = await _reconcile(uow, gateway, job_id=job.id)
    second = await _reconcile(uow, gateway, job_id=job.id)
    assert (first.outcomes, second.outcomes) == ([("evt-1", "applied")], [("evt-1", "duplicate")])
    assert second.job.status == IngestionStatus.EXTRACTED


@pytest.mark.asyncio
async def test_reconcile_never_trusts_the_reported_state_alone() -> None:
    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow)
    result = await _reconcile(uow, StatusGateway(_status(job, [], state="succeeded")), job_id=job.id)
    assert (result.outcomes, result.job.status) == ([], IngestionStatus.PROCESSING)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [{"external_task_id": "task-other"}, {"job_id": "job-other"}, {"attempt_count": 9}, {"run_number": 9}],
)
async def test_a_report_on_another_task_is_refused(override) -> None:
    from app.application.content.job_handlers import ReconcileMismatchError

    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow)
    with pytest.raises(ReconcileMismatchError):
        await _reconcile(uow, StatusGateway(_status(job, [], **override)), job_id=job.id)
    assert job.status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_events_for_another_job_or_malformed_are_rejected_not_applied() -> None:
    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow)
    events = [
        {**_body(job, "evt-a", "job_failed"), "job_id": "other-job"},
        {"event_id": "evt-b", "job_id": job.id},
        _body(job, "evt-c", "stage_progress", stage="extracted", metrics={"pages": 1}),
    ]
    result = await _reconcile(uow, StatusGateway(_status(job, events)), job_id=job.id)
    assert result.outcomes == [("evt-a", "rejected"), ("evt-b", "rejected"), ("evt-c", "rejected")]
    assert job.status == IngestionStatus.PROCESSING
    assert uow.ingestion_events.records == {}


@pytest.mark.asyncio
async def test_reconcile_is_refused_for_other_tenants_and_inactive_jobs() -> None:
    from app.domain.content.job import InvalidJobTransition

    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow)
    gateway = StatusGateway(_status(job, []))
    with pytest.raises(ValueError, match="does not exist"):
        await _reconcile(uow, gateway, tenant_id="tenant-2", job_id=job.id)
    job.fail_processing("X", "x", is_retryable=False)
    with pytest.raises(InvalidJobTransition):
        await _reconcile(uow, gateway, job_id=job.id)
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_a_gateway_failure_changes_nothing() -> None:
    from app.infrastructure.content.ai_gateway import AIServiceGatewayError

    uow = FakeContentUnitOfWork()
    job = await _dispatched_job(uow)
    error = AIServiceGatewayError("down", error_code="AI_SERVICE_POLL_FAILED", is_retryable=True)
    with pytest.raises(AIServiceGatewayError):
        await _reconcile(uow, StatusGateway(error=error), job_id=job.id)
    assert job.status == IngestionStatus.PROCESSING

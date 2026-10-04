from __future__ import annotations

from app.application.common.uow import ContentUnitOfWorkPort
from app.application.content.job_commands import (
    CreateIngestionJobCommand,
    DispatchIngestionJobCommand,
    GetIngestionJobQuery,
    GetLatestJobForAssetQuery,
    HandleAICallbackCommand,
    ListIngestionJobsQuery,
    ReprocessAssetCommand,
    RetryIngestionJobCommand,
)
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import IngestionStatus
from app.domain.content.gateway import AIServiceIngestionGateway
from app.domain.content.job import ContentIngestionJob
from app.events.event_bus import EventBus


# Where AI-service reports processing events. Never taken from a request
# (M3 design B.3); AI-service will use its own configured URL from M3-07.
INGESTION_CALLBACK_PATH = "/content/ingestion/callbacks"


def owned_job(job: ContentIngestionJob | None, tenant_id: str, job_id: str) -> ContentIngestionJob:
    """The job if it belongs to ``tenant_id``.

    A job of another tenant, or a tenant-less (platform) job, is reported
    exactly like a missing one, so a caller learns nothing about it.
    """
    if job is None or job.tenant_id is None or job.tenant_id != tenant_id:
        raise ValueError(f"ContentIngestionJob with id '{job_id}' does not exist")
    return job


def owned_asset(asset: ContentAsset | None, tenant_id: str, asset_id: str) -> ContentAsset:
    if asset is None or asset.tenant_id is None or asset.tenant_id != tenant_id:
        raise ValueError(f"ContentAsset with id '{asset_id}' does not exist")
    return asset


class CreateIngestionJobHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(self, cmd: CreateIngestionJobCommand) -> ContentIngestionJob:
        asset = owned_asset(
            await self._uow.assets.get_asset_by_id(cmd.asset_id), cmd.tenant_id, cmd.asset_id
        )

        job = ContentIngestionJob.create(
            asset_id=asset.id,
            source_id=asset.source_id,
            tenant_id=asset.tenant_id,
            created_by=cmd.created_by,
            max_attempts=cmd.max_attempts,
            correlation_id=cmd.correlation_id,
            job_id=cmd.job_id,
        )
        job.queue()

        asset.update_ingestion_status(IngestionStatus.QUEUED)

        job_events = job.pull_events()
        asset_events = asset.pull_events()

        saved_job = await self._uow.jobs.save_job(job)
        await self._uow.assets.save_asset(asset)

        all_events = job_events + asset_events
        if self._event_bus and all_events:
            self._event_bus.publish_all(all_events)

        return saved_job


class RetryIngestionJobHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(self, cmd: RetryIngestionJobCommand) -> ContentIngestionJob:
        job = owned_job(await self._uow.jobs.get_job_by_id(cmd.job_id), cmd.tenant_id, cmd.job_id)

        job.schedule_retry(delay_seconds=cmd.delay_seconds)
        job_events = job.pull_events()
        saved_job = await self._uow.jobs.save_job(job)

        asset = await self._uow.assets.get_asset_by_id(job.asset_id)
        if asset is not None:
            asset.update_ingestion_status(IngestionStatus.QUEUED)
            await self._uow.assets.save_asset(asset)
            job_events.extend(asset.pull_events())

        if self._event_bus and job_events:
            self._event_bus.publish_all(job_events)

        return saved_job


class ReprocessAssetHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(self, cmd: ReprocessAssetCommand) -> ContentIngestionJob:
        asset = owned_asset(
            await self._uow.assets.get_asset_by_id(cmd.asset_id), cmd.tenant_id, cmd.asset_id
        )

        latest_job = await self._uow.jobs.get_latest_job_for_asset(cmd.asset_id)
        if latest_job is not None:
            new_job = latest_job.create_reprocess_run(
                created_by=cmd.created_by, correlation_id=cmd.correlation_id
            )
        else:
            new_job = ContentIngestionJob.create(
                asset_id=asset.id,
                source_id=asset.source_id,
                tenant_id=asset.tenant_id,
                created_by=cmd.created_by,
                run_number=1,
                correlation_id=cmd.correlation_id,
            )
            new_job.queue()

        asset.update_ingestion_status(IngestionStatus.QUEUED)

        job_events = new_job.pull_events()
        asset_events = asset.pull_events()

        saved_job = await self._uow.jobs.save_job(new_job)
        await self._uow.assets.save_asset(asset)

        all_events = job_events + asset_events
        if self._event_bus and all_events:
            self._event_bus.publish_all(all_events)

        return saved_job


class DispatchIngestionJobHandler:
    def __init__(
        self,
        uow: ContentUnitOfWorkPort,
        gateway: AIServiceIngestionGateway,
        event_bus: EventBus | None = None,
    ) -> None:
        self._uow = uow
        self._gateway = gateway
        self._event_bus = event_bus

    async def handle(self, cmd: DispatchIngestionJobCommand) -> ContentIngestionJob:
        job = owned_job(await self._uow.jobs.get_job_by_id(cmd.job_id), cmd.tenant_id, cmd.job_id)

        asset = await self._uow.assets.get_asset_by_id(job.asset_id)
        if asset is None:
            raise ValueError(f"ContentAsset with id '{job.asset_id}' does not exist")

        source = await self._uow.sources.get_source_by_id(job.source_id)
        if source is None:
            raise ValueError(f"ContentSource with id '{job.source_id}' does not exist")

        callback_url = INGESTION_CALLBACK_PATH

        try:
            dispatch_res = await self._gateway.dispatch_ingestion_job(
                job=job,
                asset=asset,
                source=source,
                callback_url=callback_url,
            )
            job.record_dispatch(external_task_id=dispatch_res.external_task_id)
            asset.update_ingestion_status(IngestionStatus.PROCESSING)
        except Exception as exc:
            error_code = getattr(exc, "error_code", "AI_DISPATCH_FAILED")
            is_retryable = getattr(exc, "is_retryable", True)
            job.fail(
                error_code=error_code,
                error_message=str(exc),
                is_retryable=is_retryable,
            )
            asset.update_ingestion_status(
                IngestionStatus.FAILED,
                error_code=error_code,
                error_message=str(exc),
            )
            await self._uow.jobs.save_job(job)
            await self._uow.assets.save_asset(asset)
            raise

        job_events = job.pull_events()
        asset_events = asset.pull_events()

        saved_job = await self._uow.jobs.save_job(job)
        await self._uow.assets.save_asset(asset)

        all_events = job_events + asset_events
        if self._event_bus and all_events:
            self._event_bus.publish_all(all_events)

        return saved_job


class HandleAICallbackHandler:
    def __init__(
        self,
        uow: ContentUnitOfWorkPort,
        event_bus: EventBus | None = None,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(
        self, cmd: HandleAICallbackCommand
    ) -> tuple[ContentIngestionJob | None, bool]:
        """Handles an incoming webhook callback from the AI service.

        Returns (job, already_processed_or_stale).
        """
        job = await self._uow.jobs.get_job_by_id(cmd.job_id)
        if job is None:
            return None, False

        # 1. Event Idempotency Check
        if job.is_event_processed(cmd.event_id):
            return job, True

        # 2. Stale Attempt / Run Check
        if job.is_stale_callback(
            run_number=cmd.run_number,
            attempt_count=cmd.attempt_count,
            external_task_id=cmd.external_task_id,
        ):
            return job, True

        # Record this event ID as processed
        job.record_event_processed(cmd.event_id)

        # 3. Apply state transition according to event_type
        ev_type = cmd.event_type.strip().lower()
        if ev_type == "stage_progress":
            stage = (cmd.stage or "").strip().lower()
            if stage == "extracted":
                if job.status == IngestionStatus.PROCESSING:
                    job.progress_to_extracted(cmd.metrics)
            elif stage == "chunked":
                if job.status == IngestionStatus.EXTRACTED:
                    job.progress_to_chunked(cmd.metrics)
            elif stage == "indexed":
                if job.status == IngestionStatus.CHUNKED:
                    job.progress_to_indexed(cmd.metrics)
        elif ev_type == "job_completed":
            if job.status == IngestionStatus.INDEXED:
                job.complete(cmd.metrics)
        elif ev_type == "job_failed":
            if job.status != IngestionStatus.READY:
                job.fail(
                    error_code=cmd.error_code or "AI_PROCESSING_FAILED",
                    error_message=cmd.error_message or "AI service reported job failure",
                    is_retryable=cmd.is_retryable,
                    details=cmd.details,
                )

        # 4. Synchronize asset status projection
        asset = await self._uow.assets.get_asset_by_id(job.asset_id)
        if asset is not None:
            asset.update_ingestion_status(
                job.status,
                error_code=job.error_code,
                error_message=job.error_message,
            )
            await self._uow.assets.save_asset(asset)

        job_events = job.pull_events()
        if asset is not None:
            job_events.extend(asset.pull_events())

        saved_job = await self._uow.jobs.save_job(job)

        if self._event_bus and job_events:
            self._event_bus.publish_all(job_events)

        return saved_job, False


class GetIngestionJobHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(self, query: GetIngestionJobQuery) -> ContentIngestionJob | None:
        job = await self._uow.jobs.get_job_by_id(query.job_id)
        if job is None:
            return None
        if query.tenant_id is not None and job.tenant_id is not None and job.tenant_id != query.tenant_id:
            return None
        return job


class GetLatestJobForAssetHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(
        self, query: GetLatestJobForAssetQuery
    ) -> ContentIngestionJob | None:
        job = await self._uow.jobs.get_latest_job_for_asset(query.asset_id)
        if job is None:
            return None
        if query.tenant_id is not None and job.tenant_id is not None and job.tenant_id != query.tenant_id:
            return None
        return job


class ListIngestionJobsHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(
        self, query: ListIngestionJobsQuery
    ) -> tuple[list[ContentIngestionJob], int]:
        return await self._uow.jobs.list_jobs(
            tenant_id=query.tenant_id,
            asset_id=query.asset_id,
            source_id=query.source_id,
            status=query.status,
            limit=query.limit,
            offset=query.offset,
        )

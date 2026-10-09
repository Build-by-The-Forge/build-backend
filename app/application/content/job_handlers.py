from __future__ import annotations

from datetime import datetime, timezone

from app.application.common.uow import ContentUnitOfWorkPort
from app.application.identity.ports.security_events import (
    SecurityEvent,
    SecurityEventRecorder,
)
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
from app.domain.content.gateway import AIServiceIngestionGateway, IngestionDispatchActor
from app.domain.content.ingestion_event import (
    IngestionEventRecord,
    canonical_event_digest,
)
from app.domain.content.job import CallbackOutcome, ContentIngestionJob
from app.events.event_bus import EventBus


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

        # The signed context names the job's own tenant (owned_job checked it
        # is the caller's). No callback URL is sent: AI-service reports only
        # to its configured BACKEND_CALLBACK_URL.
        actor = IngestionDispatchActor(
            tenant_id=job.tenant_id or cmd.tenant_id,
            user_id=cmd.user_id,
            membership_id=cmd.membership_id,
            role=cmd.role,
            permission=cmd.permission,
        )

        # Only a queued job whose retry delay has elapsed is sent; anything
        # else is refused before AI-service is contacted.
        job.ensure_dispatchable()

        try:
            dispatch_res = await self._gateway.dispatch_ingestion_job(
                job=job,
                asset=asset,
                source=source,
                actor=actor,
            )
            job.record_dispatch(external_task_id=dispatch_res.external_task_id)
            asset.update_ingestion_status(IngestionStatus.PROCESSING)
        except Exception as exc:
            error_code = getattr(exc, "error_code", "AI_DISPATCH_FAILED")
            is_retryable = getattr(exc, "is_retryable", True)
            job.fail_dispatch(
                error_code=error_code,
                error_message=str(exc),
                is_retryable=is_retryable,
            )
            asset.update_ingestion_status(
                IngestionStatus.FAILED,
                error_code=error_code,
                error_message=str(exc),
            )
            # queued -> failed is a recorded business outcome, not an error to
            # roll back: return normally so the unit of work commits it, and
            # let the caller report the failure from the job's state.
            saved_failed = await self._uow.jobs.save_job(job)
            await self._uow.assets.save_asset(asset)
            failure_events = job.pull_events() + asset.pull_events()
            if self._event_bus and failure_events:
                self._event_bus.publish_all(failure_events)
            return saved_failed

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
        security_events: SecurityEventRecorder | None = None,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus
        self._security_events = security_events

    async def handle(
        self, cmd: HandleAICallbackCommand
    ) -> tuple[ContentIngestionJob | None, CallbackOutcome | None]:
        """Apply one verified AI-service processing event.

        In one transaction: lock the job row, check the event ledger, apply
        the event through the state machine, and record its outcome. Returns
        (None, None) when the job is unknown or not the signed tenant's,
        otherwise the job and the outcome. NOT_ALLOWED and CONFLICT record
        nothing, so the event id is not consumed. Raises InvalidStageEvidence
        when a stage lacks its evidence.
        """
        job = await self._uow.jobs.get_job_for_update(cmd.job_id)
        # Unknown, platform-owned and other tenants' jobs all look the same:
        # absent. Nothing is created or changed.
        if job is None or job.tenant_id is None or job.tenant_id != cmd.tenant_id:
            return None, None

        digest = canonical_event_digest(
            job_id=cmd.job_id,
            event_type=cmd.event_type,
            run_number=cmd.run_number,
            attempt_count=cmd.attempt_count,
            external_task_id=cmd.external_task_id,
            stage=cmd.stage,
            metrics=cmd.metrics,
            error_code=cmd.error_code,
            error_message=cmd.error_message,
            is_retryable=cmd.is_retryable,
            details=cmd.details,
        )
        recorded = await self._uow.ingestion_events.get(cmd.event_id)
        if recorded is not None:
            if recorded.job_id != job.id or (
                recorded.payload_sha256 is not None and recorded.payload_sha256 != digest
            ):
                await self._record_conflict(cmd, recorded.job_id)
                return job, CallbackOutcome.CONFLICT
            if recorded.payload_sha256 is None:
                # Seen before M3-08: handled then, content cannot be compared.
                return job, CallbackOutcome.LEGACY
            return job, CallbackOutcome.DUPLICATE

        outcome = job.apply_callback(
            event_type=cmd.event_type,
            run_number=cmd.run_number,
            attempt_count=cmd.attempt_count,
            external_task_id=cmd.external_task_id,
            stage=cmd.stage,
            metrics=cmd.metrics,
            error_code=cmd.error_code,
            error_message=cmd.error_message,
            is_retryable=cmd.is_retryable,
            details=cmd.details,
        )
        if outcome is CallbackOutcome.NOT_ALLOWED:
            return job, outcome

        await self._uow.ingestion_events.add(
            IngestionEventRecord(
                event_id=cmd.event_id,
                job_id=job.id,
                tenant_id=job.tenant_id,
                run_number=cmd.run_number,
                attempt_count=cmd.attempt_count,
                external_task_id=cmd.external_task_id,
                event_type=cmd.event_type,
                stage=cmd.stage,
                payload_sha256=digest,
                outcome=outcome,
                received_at=datetime.now(timezone.utc),
            )
        )
        if outcome is not CallbackOutcome.APPLIED:
            return job, outcome

        events = job.pull_events()
        asset = await self._uow.assets.get_asset_by_id(job.asset_id)
        if asset is not None:
            asset.update_ingestion_status(
                job.status,
                error_code=job.error_code,
                error_message=job.error_message,
            )
            await self._uow.assets.save_asset(asset)
            events.extend(asset.pull_events())

        saved_job = await self._uow.jobs.save_job(job)
        if self._event_bus and events:
            self._event_bus.publish_all(events)
        return saved_job, outcome

    async def _record_conflict(self, cmd: HandleAICallbackCommand, recorded_job_id: str) -> None:
        if self._security_events is None:
            return
        await self._security_events.record(
            SecurityEvent.AI_CALLBACK_EVENT_CONFLICT,
            metadata={
                "event_id": cmd.event_id,
                "job_id": cmd.job_id,
                "recorded_job_id": recorded_job_id,
                "tenant_id": cmd.tenant_id,
                "external_task_id": cmd.external_task_id,
            },
        )


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

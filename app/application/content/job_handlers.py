from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.common.uow import ContentUnitOfWorkPort
from app.application.content.job_commands import (
    CreateIngestionJobCommand,
    DispatchIngestionJobCommand,
    GetIngestionJobQuery,
    GetLatestJobForAssetQuery,
    HandleAICallbackCommand,
    ListIngestionJobsQuery,
    ReconcileIngestionJobCommand,
    ReprocessAssetCommand,
    RetryIngestionJobCommand,
)
from app.application.content.upload import managed_storage_key
from app.application.identity.ports.security_events import (
    SecurityEvent,
    SecurityEventRecorder,
)
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import IngestionStatus
from app.domain.content.gateway import AIServiceIngestionGateway, IngestionDispatchActor
from app.domain.content.ingestion_event import (
    IngestionEventRecord,
    canonical_event_digest,
)
from app.domain.content.job import (
    ACTIVE_STATUSES,
    CallbackOutcome,
    ContentIngestionJob,
    InvalidJobTransition,
    InvalidStageEvidence,
)
from app.domain.content.storage import (
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    ObjectStorageUnavailableError,
)
from app.events.event_bus import EventBus


def owned_job(job: ContentIngestionJob | None, tenant_id: str, job_id: str) -> ContentIngestionJob:
    """The job if it belongs to ``tenant_id``.

    A job of another tenant, or a tenant-less (platform) job, is reported
    exactly like a missing one, so a caller learns nothing about it.
    """
    if job is None or job.tenant_id is None or job.tenant_id != tenant_id:
        raise ValueError(f"ContentIngestionJob with id '{job_id}' does not exist")
    return job


class UnmanagedAssetError(ValueError):
    """The asset's storage_uri is not the server-managed reference for its
    row (design section 10): it is never queued or sent to the AI-service."""

    code = "ASSET_NOT_IN_MANAGED_STORAGE"


def require_managed_storage(asset: ContentAsset, bucket: str) -> str:
    key = managed_storage_key(asset, bucket)
    if key is None:
        raise UnmanagedAssetError("the asset is not in managed storage, so it cannot be processed; upload it instead")
    return key


# Dispatch refusals about the asset itself; they are not AI-service errors.
ASSET_DISPATCH_REFUSALS = frozenset({"ASSET_NOT_IN_MANAGED_STORAGE", "ASSET_OBJECT_MISSING", "ASSET_OBJECT_MISMATCH"})


def owned_asset(asset: ContentAsset | None, tenant_id: str, asset_id: str) -> ContentAsset:
    if asset is None or asset.tenant_id is None or asset.tenant_id != tenant_id:
        raise ValueError(f"ContentAsset with id '{asset_id}' does not exist")
    return asset


class CreateIngestionJobHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None, *, bucket: str) -> None:
        self._uow = uow
        self._event_bus = event_bus
        self._bucket = bucket

    async def handle(self, cmd: CreateIngestionJobCommand) -> ContentIngestionJob:
        asset = owned_asset(await self._uow.assets.get_asset_by_id(cmd.asset_id), cmd.tenant_id, cmd.asset_id)
        require_managed_storage(asset, self._bucket)

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
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None, *, bucket: str) -> None:
        self._uow = uow
        self._event_bus = event_bus
        self._bucket = bucket

    async def handle(self, cmd: ReprocessAssetCommand) -> ContentIngestionJob:
        asset = owned_asset(await self._uow.assets.get_asset_by_id(cmd.asset_id), cmd.tenant_id, cmd.asset_id)
        require_managed_storage(asset, self._bucket)

        latest_job = await self._uow.jobs.get_latest_job_for_asset(cmd.asset_id)
        if latest_job is not None:
            new_job = latest_job.create_reprocess_run(created_by=cmd.created_by, correlation_id=cmd.correlation_id)
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
        *,
        storage: Callable[[], ObjectStorage],
        bucket: str,
    ) -> None:
        self._uow = uow
        self._gateway = gateway
        self._event_bus = event_bus
        # Required, with no default: no configuration dispatches an asset
        # whose object was not checked (design section 10).
        self._storage = storage
        self._bucket = bucket

    async def _object_refusal(self, asset: ContentAsset) -> tuple[str, str, bool] | None:
        """Why the asset must not reach the AI-service, as (code, message,
        retryable), or None when its managed object exists and matches."""
        key = managed_storage_key(asset, self._bucket)
        if key is None:
            return ("ASSET_NOT_IN_MANAGED_STORAGE", "the asset is not in managed storage", False)
        try:
            info = await self._storage().head(key)
        except ObjectNotFoundError:
            return ("ASSET_OBJECT_MISSING", "the asset's stored object does not exist", False)
        except ObjectStorageUnavailableError:
            return ("OBJECT_STORAGE_UNAVAILABLE", "object storage is unavailable; retry later", True)
        except ObjectStorageError as exc:
            code = getattr(exc, "error_code", "OBJECT_STORAGE_FAILURE")
            return (code, "the asset's stored object could not be checked", True)
        if info.size_bytes != asset.file_size_bytes or (info.sha256 is not None and info.sha256 != asset.content_sha256):
            return ("ASSET_OBJECT_MISMATCH", "the asset's stored object does not match its recorded size or SHA-256", False)
        return None

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

        # Only a managed, existing, matching object reaches the AI-service.
        refusal = await self._object_refusal(asset)
        if refusal is not None:
            code, message, retryable = refusal
            return await self._record_dispatch_failure(job, asset, code, message, retryable)

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
            return await self._record_dispatch_failure(
                job,
                asset,
                getattr(exc, "error_code", "AI_DISPATCH_FAILED"),
                str(exc),
                getattr(exc, "is_retryable", True),
            )

        job_events = job.pull_events()
        asset_events = asset.pull_events()

        saved_job = await self._uow.jobs.save_job(job)
        await self._uow.assets.save_asset(asset)

        all_events = job_events + asset_events
        if self._event_bus and all_events:
            self._event_bus.publish_all(all_events)

        return saved_job

    async def _record_dispatch_failure(
        self, job: ContentIngestionJob, asset: ContentAsset, error_code: str, message: str, retryable: bool
    ) -> ContentIngestionJob:
        job.fail_dispatch(error_code=error_code, error_message=message, is_retryable=retryable)
        asset.update_ingestion_status(IngestionStatus.FAILED, error_code=error_code, error_message=message)
        # queued -> failed is a recorded business outcome, not an error to
        # roll back: return normally so the unit of work commits it, and
        # let the caller report the failure from the job's state.
        saved_failed = await self._uow.jobs.save_job(job)
        await self._uow.assets.save_asset(asset)
        failure_events = job.pull_events() + asset.pull_events()
        if self._event_bus and failure_events:
            self._event_bus.publish_all(failure_events)
        return saved_failed


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

    async def handle(self, cmd: HandleAICallbackCommand) -> tuple[ContentIngestionJob | None, CallbackOutcome | None]:
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
            if recorded.job_id != job.id or (recorded.payload_sha256 is not None and recorded.payload_sha256 != digest):
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

    async def handle(self, query: GetLatestJobForAssetQuery) -> ContentIngestionJob | None:
        job = await self._uow.jobs.get_latest_job_for_asset(query.asset_id)
        if job is None:
            return None
        if query.tenant_id is not None and job.tenant_id is not None and job.tenant_id != query.tenant_id:
            return None
        return job


class ListIngestionJobsHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(self, query: ListIngestionJobsQuery) -> tuple[list[ContentIngestionJob], int]:
        return await self._uow.jobs.list_jobs(
            tenant_id=query.tenant_id,
            asset_id=query.asset_id,
            source_id=query.source_id,
            status=query.status,
            limit=query.limit,
            offset=query.offset,
        )


class ReconcileMismatchError(Exception):
    """AI-service reported on a task that is not the job's active attempt."""

    status_code = 502


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    job: ContentIngestionJob
    outcomes: list[tuple[str, str]]  # (event_id, outcome) in AI-service's order


class ReconcileIngestionJobHandler:
    """POST /content/jobs/{id}/reconcile (design B.3).

    Fetches AI-service's signed account of the job's active task and replays
    each recorded event through HandleAICallbackHandler: the same row lock,
    ledger, digest, attempt and transition rules as a delivered callback.
    Events already applied come back as duplicates; events whose delivery
    failed are applied now. AI-service's reported state alone never changes
    the job. The status is fetched before any row lock is taken.
    """

    def __init__(
        self,
        uow: ContentUnitOfWorkPort,
        gateway: AIServiceIngestionGateway,
        event_bus: EventBus | None = None,
        security_events: SecurityEventRecorder | None = None,
    ) -> None:
        self._uow = uow
        self._gateway = gateway
        self._event_bus = event_bus
        self._security_events = security_events

    async def handle(self, cmd: ReconcileIngestionJobCommand) -> ReconcileResult:
        job = owned_job(await self._uow.jobs.get_job_by_id(cmd.job_id), cmd.tenant_id, cmd.job_id)
        if job.status not in ACTIVE_STATUSES or not job.external_task_id:
            raise InvalidJobTransition(f"Only an active job can be reconciled, not one that is '{job.status.value}'.")

        status = await self._gateway.fetch_job_status(
            job.external_task_id,
            job.tenant_id or cmd.tenant_id,
            job.correlation_id or job.id,
        )
        if (
            status.external_task_id != job.external_task_id
            or status.job_id != job.id
            or status.run_number != job.run_number
            or status.attempt_count != job.attempt_count
        ):
            raise ReconcileMismatchError("AI-service reported on a task that is not this job's active attempt")

        callbacks = HandleAICallbackHandler(self._uow, self._event_bus, self._security_events)
        outcomes: list[tuple[str, str]] = []
        for body in status.events:
            event_id = str(body.get("event_id", ""))
            if body.get("job_id") != job.id:
                outcomes.append((event_id, "rejected"))
                continue
            try:
                callback = HandleAICallbackCommand(
                    job_id=job.id,
                    tenant_id=job.tenant_id or cmd.tenant_id,
                    event_id=event_id,
                    event_type=str(body["event_type"]),
                    external_task_id=str(body["external_task_id"]),
                    run_number=int(body["run_number"]),
                    attempt_count=int(body["attempt_count"]),
                    stage=body.get("stage"),
                    metrics=dict(body.get("metrics") or {}),
                    error_code=body.get("error_code"),
                    error_message=body.get("error_message"),
                    is_retryable=bool(body.get("is_retryable", False)),
                    details=dict(body.get("details") or {}),
                )
            except (KeyError, TypeError, ValueError):
                outcomes.append((event_id, "rejected"))
                continue
            if not event_id:
                outcomes.append((event_id, "rejected"))
                continue
            try:
                _, outcome = await callbacks.handle(callback)
            except InvalidStageEvidence:
                outcomes.append((event_id, "rejected"))
                continue
            outcomes.append((event_id, outcome.value if outcome else "rejected"))

        refreshed = await self._uow.jobs.get_job_by_id(job.id)
        return ReconcileResult(job=refreshed or job, outcomes=outcomes)

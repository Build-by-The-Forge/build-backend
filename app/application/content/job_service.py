from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.application.common.uow import ContentUnitOfWorkFactory, ContentUnitOfWorkPort
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
from app.application.content.job_handlers import (
    CreateIngestionJobHandler,
    DispatchIngestionJobHandler,
    GetIngestionJobHandler,
    GetLatestJobForAssetHandler,
    HandleAICallbackHandler,
    ListIngestionJobsHandler,
    ReconcileIngestionJobHandler,
    ReconcileResult,
    ReprocessAssetHandler,
    RetryIngestionJobHandler,
)
from app.application.identity.ports.security_events import SecurityEventRecorder
from app.core.config import settings
from app.domain.content.enums import IngestionStatus
from app.domain.content.gateway import AIServiceIngestionGateway
from app.domain.content.job import CallbackOutcome, ContentIngestionJob
from app.domain.content.storage import ObjectStorage
from app.events.event_bus import EventBus
from app.infrastructure.content.ai_gateway import HttpAIServiceIngestionGateway
from app.infrastructure.content.s3_object_storage import S3ObjectStorage


class ContentIngestionJobService:
    def __init__(
        self,
        uow: ContentUnitOfWorkPort | None = None,
        event_bus: EventBus | None = None,
        uow_factory: ContentUnitOfWorkFactory | None = None,
        gateway: AIServiceIngestionGateway | None = None,
        security_events: SecurityEventRecorder | None = None,
        storage_factory: Callable[[], ObjectStorage] | None = None,
        bucket: Callable[[], str] | None = None,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus or EventBus()
        self._uow_factory = uow_factory
        self._gateway = gateway or HttpAIServiceIngestionGateway()
        self._security_events = security_events
        # Only assets in managed storage are queued or dispatched, and the
        # object is checked before dispatch (design section 10). Defaults are
        # the configured storage, built when first needed, never "no check".
        self._storage_factory = storage_factory or S3ObjectStorage.from_settings
        self._bucket = bucket or (lambda: settings.object_storage_bucket)

    async def create_job(
        self,
        asset_id: str,
        tenant_id: str,
        created_by: str,
        max_attempts: int = 3,
        correlation_id: str | None = None,
        job_id: str | None = None,
    ) -> ContentIngestionJob:
        cmd = CreateIngestionJobCommand(
            asset_id=asset_id,
            tenant_id=tenant_id,
            created_by=created_by,
            max_attempts=max_attempts,
            correlation_id=correlation_id,
            job_id=job_id,
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await CreateIngestionJobHandler(uow, self._event_bus, bucket=self._bucket()).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await CreateIngestionJobHandler(self._uow, self._event_bus, bucket=self._bucket()).handle(cmd)

    async def retry_job(self, job_id: str, tenant_id: str, delay_seconds: int = 30) -> ContentIngestionJob:
        cmd = RetryIngestionJobCommand(job_id=job_id, tenant_id=tenant_id, delay_seconds=delay_seconds)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await RetryIngestionJobHandler(uow, self._event_bus).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await RetryIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def reprocess_asset(
        self,
        asset_id: str,
        tenant_id: str,
        created_by: str,
        correlation_id: str | None = None,
    ) -> ContentIngestionJob:
        cmd = ReprocessAssetCommand(
            asset_id=asset_id,
            tenant_id=tenant_id,
            created_by=created_by,
            correlation_id=correlation_id,
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await ReprocessAssetHandler(uow, self._event_bus, bucket=self._bucket()).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await ReprocessAssetHandler(self._uow, self._event_bus, bucket=self._bucket()).handle(cmd)

    async def dispatch_job(
        self,
        job_id: str,
        tenant_id: str,
        user_id: str,
        membership_id: str,
        role: str,
        permission: str,
    ) -> ContentIngestionJob:
        cmd = DispatchIngestionJobCommand(
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            membership_id=membership_id,
            role=role,
            permission=permission,
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await self._dispatch_handler(uow).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await self._dispatch_handler(self._uow).handle(cmd)

    def _dispatch_handler(self, uow: ContentUnitOfWorkPort) -> DispatchIngestionJobHandler:
        return DispatchIngestionJobHandler(
            uow, self._gateway, self._event_bus, storage=self._storage_factory, bucket=self._bucket()
        )

    async def handle_callback(
        self,
        job_id: str,
        tenant_id: str,
        event_id: str,
        event_type: str,
        external_task_id: str,
        run_number: int,
        attempt_count: int,
        stage: str | None = None,
        metrics: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        is_retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> tuple[ContentIngestionJob | None, CallbackOutcome | None]:
        cmd = HandleAICallbackCommand(
            job_id=job_id,
            tenant_id=tenant_id,
            event_id=event_id,
            event_type=event_type,
            stage=stage,
            external_task_id=external_task_id,
            run_number=run_number,
            attempt_count=attempt_count,
            metrics=metrics or {},
            error_code=error_code,
            error_message=error_message,
            is_retryable=is_retryable,
            details=details or {},
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await HandleAICallbackHandler(uow, self._event_bus, self._security_events).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await HandleAICallbackHandler(self._uow, self._event_bus, self._security_events).handle(cmd)

    async def get_job(self, job_id: str, tenant_id: str | None = None) -> ContentIngestionJob | None:
        query = GetIngestionJobQuery(job_id=job_id, tenant_id=tenant_id)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await GetIngestionJobHandler(uow).handle(query)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await GetIngestionJobHandler(self._uow).handle(query)

    async def get_latest_job_for_asset(self, asset_id: str, tenant_id: str | None = None) -> ContentIngestionJob | None:
        query = GetLatestJobForAssetQuery(asset_id=asset_id, tenant_id=tenant_id)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await GetLatestJobForAssetHandler(uow).handle(query)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await GetLatestJobForAssetHandler(self._uow).handle(query)

    async def list_jobs(
        self,
        tenant_id: str | None = None,
        asset_id: str | None = None,
        source_id: str | None = None,
        status: IngestionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentIngestionJob], int]:
        query = ListIngestionJobsQuery(
            tenant_id=tenant_id,
            asset_id=asset_id,
            source_id=source_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await ListIngestionJobsHandler(uow).handle(query)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await ListIngestionJobsHandler(self._uow).handle(query)

    async def reconcile_job(self, job_id: str, tenant_id: str) -> ReconcileResult:
        cmd = ReconcileIngestionJobCommand(job_id=job_id, tenant_id=tenant_id)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await ReconcileIngestionJobHandler(uow, self._gateway, self._event_bus, self._security_events).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await ReconcileIngestionJobHandler(self._uow, self._gateway, self._event_bus, self._security_events).handle(cmd)

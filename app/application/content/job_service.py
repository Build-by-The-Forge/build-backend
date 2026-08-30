from __future__ import annotations

from typing import Any

from app.application.common.uow import ContentUnitOfWorkFactory, ContentUnitOfWorkPort
from app.application.content.job_commands import (
    CompleteIngestionJobCommand,
    CreateIngestionJobCommand,
    FailIngestionJobCommand,
    GetIngestionJobQuery,
    GetLatestJobForAssetQuery,
    ListIngestionJobsQuery,
    ProgressIngestionJobCommand,
    ReprocessAssetCommand,
    RetryIngestionJobCommand,
    StartIngestionJobCommand,
)
from app.application.content.job_handlers import (
    CompleteIngestionJobHandler,
    CreateIngestionJobHandler,
    FailIngestionJobHandler,
    GetIngestionJobHandler,
    GetLatestJobForAssetHandler,
    ListIngestionJobsHandler,
    ProgressIngestionJobHandler,
    ReprocessAssetHandler,
    RetryIngestionJobHandler,
    StartIngestionJobHandler,
)
from app.domain.content.enums import IngestionStatus
from app.domain.content.job import ContentIngestionJob
from app.events.event_bus import EventBus


class ContentIngestionJobService:
    def __init__(
        self,
        uow: ContentUnitOfWorkPort | None = None,
        event_bus: EventBus | None = None,
        uow_factory: ContentUnitOfWorkFactory | None = None,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus or EventBus()
        self._uow_factory = uow_factory

    async def create_job(
        self,
        asset_id: str,
        created_by: str,
        max_attempts: int = 3,
        correlation_id: str | None = None,
        job_id: str | None = None,
    ) -> ContentIngestionJob:
        cmd = CreateIngestionJobCommand(
            asset_id=asset_id,
            created_by=created_by,
            max_attempts=max_attempts,
            correlation_id=correlation_id,
            job_id=job_id,
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await CreateIngestionJobHandler(uow, self._event_bus).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await CreateIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def start_job(
        self, job_id: str, stage: str = "parsing"
    ) -> ContentIngestionJob:
        cmd = StartIngestionJobCommand(job_id=job_id, stage=stage)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await StartIngestionJobHandler(uow, self._event_bus).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await StartIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def progress_job(
        self,
        job_id: str,
        target_stage: str,
        metrics: dict[str, Any] | None = None,
    ) -> ContentIngestionJob:
        cmd = ProgressIngestionJobCommand(
            job_id=job_id,
            target_stage=target_stage,
            metrics=metrics or {},
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await ProgressIngestionJobHandler(uow, self._event_bus).handle(
                    cmd
                )
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await ProgressIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def complete_job(
        self, job_id: str, metrics: dict[str, Any] | None = None
    ) -> ContentIngestionJob:
        cmd = CompleteIngestionJobCommand(job_id=job_id, metrics=metrics or {})
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await CompleteIngestionJobHandler(uow, self._event_bus).handle(
                    cmd
                )
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await CompleteIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def fail_job(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        is_retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> ContentIngestionJob:
        cmd = FailIngestionJobCommand(
            job_id=job_id,
            error_code=error_code,
            error_message=error_message,
            is_retryable=is_retryable,
            details=details or {},
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await FailIngestionJobHandler(uow, self._event_bus).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await FailIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def retry_job(
        self, job_id: str, delay_seconds: int = 30
    ) -> ContentIngestionJob:
        cmd = RetryIngestionJobCommand(job_id=job_id, delay_seconds=delay_seconds)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await RetryIngestionJobHandler(uow, self._event_bus).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await RetryIngestionJobHandler(self._uow, self._event_bus).handle(cmd)

    async def reprocess_asset(
        self,
        asset_id: str,
        created_by: str,
        correlation_id: str | None = None,
    ) -> ContentIngestionJob:
        cmd = ReprocessAssetCommand(
            asset_id=asset_id,
            created_by=created_by,
            correlation_id=correlation_id,
        )
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await ReprocessAssetHandler(uow, self._event_bus).handle(cmd)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await ReprocessAssetHandler(self._uow, self._event_bus).handle(cmd)

    async def get_job(
        self, job_id: str, tenant_id: str | None = None
    ) -> ContentIngestionJob | None:
        query = GetIngestionJobQuery(job_id=job_id, tenant_id=tenant_id)
        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                return await GetIngestionJobHandler(uow).handle(query)
        if self._uow is None:
            raise RuntimeError("ContentIngestionJobService requires uow or uow_factory")
        return await GetIngestionJobHandler(self._uow).handle(query)

    async def get_latest_job_for_asset(
        self, asset_id: str, tenant_id: str | None = None
    ) -> ContentIngestionJob | None:
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

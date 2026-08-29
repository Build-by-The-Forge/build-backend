from __future__ import annotations

from datetime import datetime

from app.application.common.uow import CurriculumUnitOfWorkFactory
from app.application.curriculum.source_commands import (
    GetCurriculumSourceCommand,
    ListCurriculumSnapshotsCommand,
    ListCurriculumSourcesCommand,
    RecordCurriculumSnapshotCommand,
    RegisterCurriculumSourceCommand,
)
from app.application.curriculum.source_handlers import (
    GetCurriculumSourceHandler,
    ListCurriculumSnapshotsHandler,
    ListCurriculumSourcesHandler,
    RecordCurriculumSnapshotHandler,
    RegisterCurriculumSourceHandler,
)
from app.domain.curriculum.source import CurriculumSnapshot, CurriculumSource
from app.domain.repositories.curriculum_source import CurriculumSourceRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class CurriculumSourceService:
    def __init__(
        self,
        repository: CurriculumSourceRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: CurriculumUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def register_source(
        self,
        code: str,
        name: str,
        base_url: str,
        source_type: str = "official_benchmark",
        sync_frequency_days: int = 30,
        parser_version: str = "v1.0",
    ) -> CurriculumSource:
        command = RegisterCurriculumSourceCommand(
            code=code,
            name=name,
            base_url=base_url,
            source_type=source_type,
            sync_frequency_days=sync_frequency_days,
            parser_version=parser_version,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                source = await RegisterCurriculumSourceHandler(uow.sources).handle(
                    command
                )
                events = source.pull_events()
            self._publish_events(events)
            return source

        source = await RegisterCurriculumSourceHandler(
            self._required_repository()
        ).handle(command)
        self._publish_events(source.pull_events())
        return source

    async def get_source(self, source_id: str) -> CurriculumSource | None:
        command = GetCurriculumSourceCommand(source_id=source_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetCurriculumSourceHandler(uow.sources).handle(command)
        return await GetCurriculumSourceHandler(self._required_repository()).handle(
            command
        )

    async def list_sources(self, status: str | None = None) -> list[CurriculumSource]:
        command = ListCurriculumSourcesCommand(status=status)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListCurriculumSourcesHandler(uow.sources).handle(command)
        return await ListCurriculumSourcesHandler(self._required_repository()).handle(
            command
        )

    async def record_snapshot(
        self,
        source_id: str,
        source_url: str,
        content_sha256: str,
        raw_artifact_uri: str,
        parser_version: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> tuple[CurriculumSnapshot, bool]:
        command = RecordCurriculumSnapshotCommand(
            source_id=source_id,
            source_url=source_url,
            content_sha256=content_sha256,
            raw_artifact_uri=raw_artifact_uri,
            parser_version=parser_version,
            retrieved_at=retrieved_at,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                snapshot, drift, events = await RecordCurriculumSnapshotHandler(
                    uow.sources
                ).handle(command)
            self._publish_events(events)
            return snapshot, drift

        snapshot, drift, events = await RecordCurriculumSnapshotHandler(
            self._required_repository()
        ).handle(command)
        self._publish_events(events)
        return snapshot, drift

    async def list_snapshots(
        self, source_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[CurriculumSnapshot], int] | None:
        command = ListCurriculumSnapshotsCommand(
            source_id=source_id, limit=limit, offset=offset
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListCurriculumSnapshotsHandler(uow.sources).handle(command)
        return await ListCurriculumSnapshotsHandler(self._required_repository()).handle(
            command
        )

    def _required_repository(self) -> CurriculumSourceRepository:
        if self.repository is None:
            raise ValueError("curriculum source repository is required")
        return self.repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

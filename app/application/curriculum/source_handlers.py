from __future__ import annotations

from app.application.curriculum.source_commands import (
    GetCurriculumSourceCommand,
    ListCurriculumSnapshotsCommand,
    ListCurriculumSourcesCommand,
    RecordCurriculumSnapshotCommand,
    RegisterCurriculumSourceCommand,
)
from app.domain.curriculum.source import CurriculumSnapshot, CurriculumSource
from app.domain.repositories.curriculum_source import CurriculumSourceRepository
from app.events.base import DomainEvent


class RegisterCurriculumSourceHandler:
    def __init__(self, repository: CurriculumSourceRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: RegisterCurriculumSourceCommand
    ) -> CurriculumSource:
        existing = await self.repository.get_source_by_code(command.code)
        if existing is not None:
            raise ValueError(
                f"curriculum source with code '{command.code}' already exists"
            )

        source = CurriculumSource.create(
            code=command.code,
            name=command.name,
            base_url=command.base_url,
            source_type=command.source_type,
            sync_frequency_days=command.sync_frequency_days,
            parser_version=command.parser_version,
        )
        return await self.repository.save_source(source)


class GetCurriculumSourceHandler:
    def __init__(self, repository: CurriculumSourceRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: GetCurriculumSourceCommand
    ) -> CurriculumSource | None:
        return await self.repository.get_source_by_id(command.source_id)


class ListCurriculumSourcesHandler:
    def __init__(self, repository: CurriculumSourceRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: ListCurriculumSourcesCommand
    ) -> list[CurriculumSource]:
        return await self.repository.list_sources(status=command.status)


class RecordCurriculumSnapshotHandler:
    def __init__(self, repository: CurriculumSourceRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: RecordCurriculumSnapshotCommand
    ) -> tuple[CurriculumSnapshot, bool, list[DomainEvent]]:
        source = await self.repository.get_source_by_id(command.source_id)
        if source is None:
            raise ValueError(f"curriculum source '{command.source_id}' not found")

        # Idempotency check: see if snapshot with identical hash already exists
        existing_snapshot = await self.repository.get_snapshot_by_hash(
            source_id=command.source_id,
            content_sha256=command.content_sha256,
        )
        if existing_snapshot is not None:
            return existing_snapshot, False, []

        # New content hash -> create and persist immutable snapshot
        snapshot = source.create_snapshot(
            source_url=command.source_url,
            content_sha256=command.content_sha256,
            raw_artifact_uri=command.raw_artifact_uri,
            parser_version=command.parser_version,
            retrieved_at=command.retrieved_at,
        )
        saved_snapshot = await self.repository.save_snapshot(snapshot)
        await self.repository.save_source(source)
        events = source.pull_events()
        return saved_snapshot, True, events


class ListCurriculumSnapshotsHandler:
    def __init__(self, repository: CurriculumSourceRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: ListCurriculumSnapshotsCommand
    ) -> tuple[list[CurriculumSnapshot], int] | None:
        source = await self.repository.get_source_by_id(command.source_id)
        if source is None:
            return None
        return await self.repository.list_snapshots(
            source_id=command.source_id,
            limit=command.limit,
            offset=command.offset,
        )

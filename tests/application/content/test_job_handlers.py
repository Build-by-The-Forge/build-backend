from datetime import datetime, timezone
import pytest

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
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AssetStatus,
    AuthorityLevel,
    ContentSourceType,
    IngestionStatus,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.events.event_bus import EventBus


class InMemoryContentSourceRepo:
    def __init__(self) -> None:
        self.sources: dict[str, ContentSource] = {}

    async def save_source(self, source: ContentSource) -> ContentSource:
        self.sources[source.id] = source
        return source

    async def get_source_by_id(self, source_id: str) -> ContentSource | None:
        return self.sources.get(source_id)

    async def get_source_by_code(
        self, code: str, tenant_id: str | None = None
    ) -> ContentSource | None:
        for s in self.sources.values():
            if s.code == code and s.tenant_id == tenant_id:
                return s
        return None

    async def list_sources(
        self,
        tenant_id: str | None = None,
        source_type: ContentSourceType | None = None,
        authority_level: AuthorityLevel | None = None,
        status: SourceStatus | None = None,
        include_platform: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentSource], int]:
        results = list(self.sources.values())
        return results[offset : offset + limit], len(results)


class InMemoryContentAssetRepo:
    def __init__(self) -> None:
        self.assets: dict[str, ContentAsset] = {}

    async def save_asset(self, asset: ContentAsset) -> ContentAsset:
        self.assets[asset.id] = asset
        return asset

    async def get_asset_by_id(self, asset_id: str) -> ContentAsset | None:
        return self.assets.get(asset_id)

    async def get_asset_by_hash(
        self, content_sha256: str, tenant_id: str | None = None
    ) -> ContentAsset | None:
        clean = content_sha256.strip().lower()
        for a in self.assets.values():
            if a.content_sha256 == clean and a.tenant_id == tenant_id:
                return a
        return None

    async def list_assets_by_source(
        self, source_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ContentAsset], int]:
        res = [a for a in self.assets.values() if a.source_id == source_id]
        return res[offset : offset + limit], len(res)

    async def list_assets(
        self,
        tenant_id: str | None = None,
        source_id: str | None = None,
        status: AssetStatus | None = None,
        ingestion_status: IngestionStatus | None = None,
        include_platform: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentAsset], int]:
        res = list(self.assets.values())
        if tenant_id is not None:
            if include_platform:
                res = [a for a in res if a.tenant_id == tenant_id or a.tenant_id is None]
            else:
                res = [a for a in res if a.tenant_id == tenant_id]
        if source_id is not None:
            res = [a for a in res if a.source_id == source_id]
        if status is not None:
            res = [a for a in res if a.status == status]
        if ingestion_status is not None:
            res = [a for a in res if a.ingestion_status == ingestion_status]
        return res[offset : offset + limit], len(res)


class InMemoryContentJobRepo:
    def __init__(self) -> None:
        self.jobs: dict[str, ContentIngestionJob] = {}

    async def save_job(self, job: ContentIngestionJob) -> ContentIngestionJob:
        self.jobs[job.id] = job
        return job

    async def get_job_by_id(self, job_id: str) -> ContentIngestionJob | None:
        return self.jobs.get(job_id)

    async def get_latest_job_for_asset(
        self, asset_id: str
    ) -> ContentIngestionJob | None:
        matches = [j for j in self.jobs.values() if j.asset_id == asset_id]
        if not matches:
            return None
        matches.sort(key=lambda j: (j.run_number, j.created_at), reverse=True)
        return matches[0]

    async def list_jobs_for_asset(
        self, asset_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ContentIngestionJob], int]:
        matches = [j for j in self.jobs.values() if j.asset_id == asset_id]
        matches.sort(key=lambda j: (j.run_number, j.created_at), reverse=True)
        return matches[offset : offset + limit], len(matches)

    async def list_pending_jobs(
        self, tenant_id: str | None = None, limit: int = 50
    ) -> list[ContentIngestionJob]:
        now = datetime.now(timezone.utc)
        matches = [
            j
            for j in self.jobs.values()
            if (
                j.status == IngestionStatus.QUEUED
                or (
                    j.status == IngestionStatus.FAILED
                    and j.is_retryable
                    and j.next_retry_at is not None
                    and j.next_retry_at <= now
                )
            )
            and (tenant_id is None or j.tenant_id == tenant_id)
        ]
        return matches[:limit]

    async def list_jobs(
        self,
        tenant_id: str | None = None,
        asset_id: str | None = None,
        source_id: str | None = None,
        status: IngestionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentIngestionJob], int]:
        res = list(self.jobs.values())
        if tenant_id is not None:
            res = [j for j in res if j.tenant_id == tenant_id or j.tenant_id is None]
        if asset_id is not None:
            res = [j for j in res if j.asset_id == asset_id]
        if source_id is not None:
            res = [j for j in res if j.source_id == source_id]
        if status is not None:
            res = [j for j in res if j.status == status]
        res.sort(key=lambda j: j.created_at, reverse=True)
        return res[offset : offset + limit], len(res)


class FakeContentUnitOfWork:
    def __init__(self) -> None:
        self.sources = InMemoryContentSourceRepo()
        self.assets = InMemoryContentAssetRepo()
        self.jobs = InMemoryContentJobRepo()


@pytest.mark.asyncio
async def test_create_and_start_job_handler() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()

    # Create Asset
    asset = ContentAsset.create(
        source_id="csrc-1",
        file_name="intro.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="a" * 64,
        storage_uri="s3://bucket/intro.pdf",
        created_by="usr-1",
        created_by_email="usr-1@example.com",
        tenant_id="tenant-1",
    )
    await uow.assets.save_asset(asset)

    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(
        CreateIngestionJobCommand(asset_id=asset.id, created_by="usr-1")
    )

    assert job.asset_id == asset.id
    assert job.status == IngestionStatus.QUEUED
    assert asset.ingestion_status == IngestionStatus.QUEUED
    assert len(uow.jobs.jobs) == 1

    # Start job
    start_handler = StartIngestionJobHandler(uow, bus)
    started_job = await start_handler.handle(
        StartIngestionJobCommand(job_id=job.id, stage="parsing")
    )

    assert started_job.status == IngestionStatus.PROCESSING
    assert started_job.current_stage == "parsing"
    assert asset.ingestion_status == IngestionStatus.PROCESSING


@pytest.mark.asyncio
async def test_progress_and_complete_job_handler() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()

    asset = ContentAsset.create(
        source_id="csrc-1",
        file_name="intro.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="a" * 64,
        storage_uri="s3://bucket/intro.pdf",
        created_by="usr-1",
        created_by_email="usr-1@example.com",
        tenant_id="tenant-1",
    )
    await uow.assets.save_asset(asset)

    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(
        CreateIngestionJobCommand(asset_id=asset.id, created_by="usr-1")
    )

    start_handler = StartIngestionJobHandler(uow, bus)
    job = await start_handler.handle(
        StartIngestionJobCommand(job_id=job.id, stage="parsing")
    )

    progress_handler = ProgressIngestionJobHandler(uow, bus)

    # 1. Extracted
    job = await progress_handler.handle(
        ProgressIngestionJobCommand(job_id=job.id, target_stage="extracted")
    )
    assert job.status == IngestionStatus.EXTRACTED
    assert asset.ingestion_status == IngestionStatus.EXTRACTED

    # 2. Chunked
    job = await progress_handler.handle(
        ProgressIngestionJobCommand(job_id=job.id, target_stage="chunked")
    )
    assert job.status == IngestionStatus.CHUNKED
    assert asset.ingestion_status == IngestionStatus.CHUNKED

    # 3. Indexed
    job = await progress_handler.handle(
        ProgressIngestionJobCommand(job_id=job.id, target_stage="indexed")
    )
    assert job.status == IngestionStatus.INDEXED
    assert asset.ingestion_status == IngestionStatus.INDEXED

    # 4. Complete
    complete_handler = CompleteIngestionJobHandler(uow, bus)
    job = await complete_handler.handle(
        CompleteIngestionJobCommand(job_id=job.id, metrics={"indexed": 50})
    )
    assert job.status == IngestionStatus.READY
    assert asset.ingestion_status == IngestionStatus.READY


@pytest.mark.asyncio
async def test_fail_and_retry_job_handler() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()

    asset = ContentAsset.create(
        source_id="csrc-1",
        file_name="intro.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="a" * 64,
        storage_uri="s3://bucket/intro.pdf",
        created_by="usr-1",
        created_by_email="usr-1@example.com",
        tenant_id="tenant-1",
    )
    await uow.assets.save_asset(asset)

    create_handler = CreateIngestionJobHandler(uow, bus)
    job = await create_handler.handle(
        CreateIngestionJobCommand(asset_id=asset.id, created_by="usr-1", max_attempts=3)
    )

    start_handler = StartIngestionJobHandler(uow, bus)
    job = await start_handler.handle(
        StartIngestionJobCommand(job_id=job.id, stage="parsing")
    )

    fail_handler = FailIngestionJobHandler(uow, bus)
    job = await fail_handler.handle(
        FailIngestionJobCommand(
            job_id=job.id,
            error_code="TIMEOUT",
            error_message="Gateway timeout",
            is_retryable=True,
        )
    )
    assert job.status == IngestionStatus.FAILED
    assert asset.ingestion_status == IngestionStatus.FAILED

    retry_handler = RetryIngestionJobHandler(uow, bus)
    job = await retry_handler.handle(
        RetryIngestionJobCommand(job_id=job.id, delay_seconds=15)
    )
    assert job.status == IngestionStatus.QUEUED
    assert job.attempt_count == 2
    assert asset.ingestion_status == IngestionStatus.QUEUED


@pytest.mark.asyncio
async def test_reprocess_asset_handler() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()

    asset = ContentAsset.create(
        source_id="csrc-1",
        file_name="intro.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="a" * 64,
        storage_uri="s3://bucket/intro.pdf",
        created_by="usr-1",
        created_by_email="usr-1@example.com",
        tenant_id="tenant-1",
    )
    await uow.assets.save_asset(asset)

    create_handler = CreateIngestionJobHandler(uow, bus)
    job1 = await create_handler.handle(
        CreateIngestionJobCommand(asset_id=asset.id, created_by="usr-1")
    )
    await StartIngestionJobHandler(uow, bus).handle(StartIngestionJobCommand(job_id=job1.id))
    await ProgressIngestionJobHandler(uow, bus).handle(ProgressIngestionJobCommand(job_id=job1.id, target_stage="extracted"))
    await ProgressIngestionJobHandler(uow, bus).handle(ProgressIngestionJobCommand(job_id=job1.id, target_stage="chunked"))
    await ProgressIngestionJobHandler(uow, bus).handle(ProgressIngestionJobCommand(job_id=job1.id, target_stage="indexed"))
    await CompleteIngestionJobHandler(uow, bus).handle(CompleteIngestionJobCommand(job_id=job1.id))

    reprocess_handler = ReprocessAssetHandler(uow, bus)
    new_job = await reprocess_handler.handle(
        ReprocessAssetCommand(asset_id=asset.id, created_by="usr-admin")
    )

    assert new_job.run_number == 2
    assert new_job.status == IngestionStatus.QUEUED
    assert new_job.attempt_count == 1
    assert asset.ingestion_status == IngestionStatus.QUEUED

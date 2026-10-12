from datetime import datetime, timezone
import pytest

from app.application.content.job_commands import (
    CreateIngestionJobCommand,
    ReprocessAssetCommand,
    RetryIngestionJobCommand,
)
from app.application.content.job_handlers import (
    CreateIngestionJobHandler,
    ReprocessAssetHandler,
    RetryIngestionJobHandler,
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
from app.domain.content.ingestion_event import IngestionEventRecord
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

    async def get_source_by_code(self, code: str, tenant_id: str | None = None) -> ContentSource | None:
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

    async def get_asset_by_hash(self, content_sha256: str, tenant_id: str | None = None) -> ContentAsset | None:
        clean = content_sha256.strip().lower()
        for a in self.assets.values():
            if a.content_sha256 == clean and a.tenant_id == tenant_id:
                return a
        return None

    async def list_assets_by_source(self, source_id: str, limit: int = 50, offset: int = 0) -> tuple[list[ContentAsset], int]:
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

    async def get_job_for_update(self, job_id: str) -> ContentIngestionJob | None:
        return self.jobs.get(job_id)

    async def get_latest_job_for_asset(self, asset_id: str) -> ContentIngestionJob | None:
        matches = [j for j in self.jobs.values() if j.asset_id == asset_id]
        if not matches:
            return None
        matches.sort(key=lambda j: (j.run_number, j.created_at), reverse=True)
        return matches[0]

    async def list_jobs_for_asset(self, asset_id: str, limit: int = 50, offset: int = 0) -> tuple[list[ContentIngestionJob], int]:
        matches = [j for j in self.jobs.values() if j.asset_id == asset_id]
        matches.sort(key=lambda j: (j.run_number, j.created_at), reverse=True)
        return matches[offset : offset + limit], len(matches)

    async def list_pending_jobs(self, tenant_id: str | None = None, limit: int = 50) -> list[ContentIngestionJob]:
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


class InMemoryIngestionEventRepo:
    def __init__(self) -> None:
        self.records: dict[str, IngestionEventRecord] = {}

    async def get(self, event_id: str) -> IngestionEventRecord | None:
        return self.records.get(event_id)

    async def add(self, record: IngestionEventRecord) -> None:
        assert record.event_id not in self.records  # the table's primary key
        self.records[record.event_id] = record


class FakeContentUnitOfWork:
    def __init__(self) -> None:
        self.sources = InMemoryContentSourceRepo()
        self.assets = InMemoryContentAssetRepo()
        self.jobs = InMemoryContentJobRepo()
        self.ingestion_events = InMemoryIngestionEventRepo()


async def _asset(uow, tenant_id="tenant-1") -> ContentAsset:
    asset = ContentAsset.create(
        source_id="csrc-1",
        file_name="intro.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=1024,
        content_sha256="a" * 64,
        storage_uri="s3://bucket/intro.pdf",
        created_by="usr-1",
        created_by_email="usr-1@example.com",
        tenant_id=tenant_id,
    )
    await uow.assets.save_asset(asset)
    return asset


async def _job(uow, bus, asset, tenant_id="tenant-1", **kwargs) -> ContentIngestionJob:
    return await CreateIngestionJobHandler(uow, bus).handle(
        CreateIngestionJobCommand(asset_id=asset.id, tenant_id=tenant_id, created_by="usr-1", **kwargs)
    )


def _to_ready(job: ContentIngestionJob) -> None:
    """Processing transitions happen only through verified AI callbacks,
    each with its stage evidence."""
    job.record_dispatch(external_task_id=f"aitask-{job.id}")
    job.progress_to_extracted({"characters": 100, "pages": 1, "method": "native_text"})
    job.progress_to_chunked({"chunks": 4})
    job.progress_to_indexed({"indexed_chunks": 4, "index": "pgvector"})
    job.complete()


@pytest.mark.asyncio
async def test_create_job_queues_it_for_the_owning_tenant() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    asset = await _asset(uow)

    job = await _job(uow, bus, asset)

    assert (job.asset_id, job.tenant_id, job.status) == (asset.id, "tenant-1", IngestionStatus.QUEUED)
    assert asset.ingestion_status == IngestionStatus.QUEUED
    assert len(uow.jobs.jobs) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("asset_tenant", ["tenant-2", None])
async def test_create_job_for_another_tenants_or_platform_asset_is_refused(asset_tenant) -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    asset = await _asset(uow, tenant_id=asset_tenant)

    with pytest.raises(ValueError, match="does not exist"):
        await _job(uow, bus, asset, tenant_id="tenant-1")
    assert uow.jobs.jobs == {}


@pytest.mark.asyncio
async def test_retry_of_a_failed_job_requeues_it() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    asset = await _asset(uow)
    job = await _job(uow, bus, asset, max_attempts=3)
    job.record_dispatch(external_task_id="aitask-1")
    job.fail_processing(error_code="TIMEOUT", error_message="Gateway timeout", is_retryable=True)

    job = await RetryIngestionJobHandler(uow, bus).handle(
        RetryIngestionJobCommand(job_id=job.id, tenant_id="tenant-1", delay_seconds=15)
    )

    assert (job.status, job.attempt_count) == (IngestionStatus.QUEUED, 2)
    assert asset.ingestion_status == IngestionStatus.QUEUED


@pytest.mark.asyncio
async def test_retry_of_another_tenants_job_is_refused() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    job = await _job(uow, bus, await _asset(uow))
    job.record_dispatch(external_task_id="aitask-1")
    job.fail_processing(error_code="TIMEOUT", error_message="Gateway timeout", is_retryable=True)

    with pytest.raises(ValueError, match="does not exist"):
        await RetryIngestionJobHandler(uow, bus).handle(RetryIngestionJobCommand(job_id=job.id, tenant_id="tenant-2"))
    assert job.status == IngestionStatus.FAILED


@pytest.mark.asyncio
async def test_reprocess_asset_starts_a_new_run() -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    asset = await _asset(uow)
    _to_ready(await _job(uow, bus, asset))

    new_job = await ReprocessAssetHandler(uow, bus).handle(
        ReprocessAssetCommand(asset_id=asset.id, tenant_id="tenant-1", created_by="usr-admin")
    )

    assert (new_job.run_number, new_job.status, new_job.attempt_count) == (2, IngestionStatus.QUEUED, 1)
    assert asset.ingestion_status == IngestionStatus.QUEUED


@pytest.mark.asyncio
@pytest.mark.parametrize("asset_tenant", ["tenant-2", None])
async def test_reprocess_of_another_tenants_or_platform_asset_is_refused(asset_tenant) -> None:
    uow, bus = FakeContentUnitOfWork(), EventBus()
    asset = await _asset(uow, tenant_id=asset_tenant)

    with pytest.raises(ValueError, match="does not exist"):
        await ReprocessAssetHandler(uow, bus).handle(
            ReprocessAssetCommand(asset_id=asset.id, tenant_id="tenant-1", created_by="usr-admin")
        )
    assert uow.jobs.jobs == {}

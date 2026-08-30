import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetMimeType,
    AuthorityLevel,
    ContentSourceType,
    IngestionStatus,
    VisibilityScope,
)
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.infrastructure.content.asset_repositories import (
    SqlAlchemyContentAssetRepository,
)
from app.infrastructure.content.job_repositories import (
    SqlAlchemyContentIngestionJobRepository,
)
from app.infrastructure.content.repositories import SqlAlchemyContentSourceRepository


@pytest.mark.asyncio
async def test_content_job_persistence_and_latest_lookup(
    session: AsyncSession,
) -> None:
    # 1. Create Source (Platform-scoped CCMAS)
    source_repo = SqlAlchemyContentSourceRepository(session)
    source = ContentSource.create(
        code="SRC_JOB_PERSIST_TEST",
        name="Job Test Source",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await source_repo.save_source(source)

    # 2. Create Asset
    asset_repo = SqlAlchemyContentAssetRepository(session)
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="lecture1.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=4096,
        content_sha256="c" * 64,
        storage_uri="s3://build/lecture1.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await asset_repo.save_asset(asset)

    # 3. Create Job 1 (Run 1)
    job_repo = SqlAlchemyContentIngestionJobRepository(session)
    job1 = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        created_by="usr-1",
        run_number=1,
    )
    job1.queue()
    job1.start()
    job1.progress_to_extracted()
    job1.progress_to_chunked()
    job1.progress_to_indexed()
    job1.complete()
    await job_repo.save_job(job1)

    # 4. Create Job 2 (Reprocess Run 2)
    job2 = job1.create_reprocess_run(created_by="usr-admin")
    await job_repo.save_job(job2)

    # Verify latest job for asset is Run 2
    latest = await job_repo.get_latest_job_for_asset(asset.id)
    assert latest is not None
    assert latest.id == job2.id
    assert latest.run_number == 2
    assert latest.status == IngestionStatus.QUEUED

    # List jobs for asset
    jobs, total = await job_repo.list_jobs_for_asset(asset.id)
    assert total == 2
    assert len(jobs) == 2
    assert jobs[0].run_number == 2
    assert jobs[1].run_number == 1


@pytest.mark.asyncio
async def test_pending_and_retryable_jobs_query(session: AsyncSession) -> None:
    source_repo = SqlAlchemyContentSourceRepository(session)
    source = ContentSource.create(
        code="SRC_RETRY_TEST",
        name="RTU Source",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await source_repo.save_source(source)

    asset_repo = SqlAlchemyContentAssetRepository(session)
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="notes.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=2048,
        content_sha256="d" * 64,
        storage_uri="s3://build/notes.pdf",
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    await asset_repo.save_asset(asset)

    job_repo = SqlAlchemyContentIngestionJobRepository(session)
    job = ContentIngestionJob.create(
        asset_id=asset.id,
        source_id=source.id,
        created_by="usr-1",
    )
    job.queue()
    await job_repo.save_job(job)

    pending = await job_repo.list_pending_jobs()
    assert len(pending) >= 1
    assert any(j.id == job.id for j in pending)

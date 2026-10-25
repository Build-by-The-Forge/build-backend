"""The dispatch boundary (P3-1 PR 3b, design section 10): only an asset in
managed storage is queued, and only one whose stored object exists and
matches its row is sent to the AI-service."""

import hashlib

import pytest

from app.application.content.job_commands import CreateIngestionJobCommand, ReprocessAssetCommand
from app.application.content.job_handlers import (
    CreateIngestionJobHandler,
    DispatchIngestionJobHandler,
    ReprocessAssetHandler,
    UnmanagedAssetError,
)
from app.application.content.upload import object_key
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetMimeType, AuthorityLevel, ContentSourceType, IngestionStatus, VisibilityScope
from app.domain.content.job import ContentIngestionJob
from app.domain.content.source import ContentSource
from app.domain.content.storage import ObjectInfo, ObjectStorageUnavailableError
from app.events.event_bus import EventBus
from tests.application.content.managed_storage import BUCKET, StoredObjects, managed
from tests.application.content.test_ai_dispatch_handlers import FakeAIGateway, dispatch_cmd
from tests.application.content.test_job_handlers import FakeContentUnitOfWork

TENANT = "tenant-1"
SHA = hashlib.sha256(b"lecture notes").hexdigest()


async def _setup(uow, objects, *, manage=True, storage_uri="s3://anywhere/notes.pdf"):
    source = ContentSource.create(
        code="SRC_GATE",
        name="Gate",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-1",
        created_by_email="u@example.com",
        tenant_id=TENANT,
    )
    await uow.sources.save_source(source)
    asset = ContentAsset.create(
        source_id=source.id,
        file_name="notes.pdf",
        mime_type=AssetMimeType.PDF,
        file_size_bytes=4096,
        content_sha256=SHA,
        storage_uri=storage_uri,
        tenant_id=TENANT,
        created_by="usr-1",
        created_by_email="u@example.com",
    )
    if manage:
        managed(asset, objects)
    await uow.assets.save_asset(asset)
    # A queued job, as one created before PR 3b may exist for any asset.
    job = ContentIngestionJob.create(asset_id=asset.id, source_id=source.id, tenant_id=TENANT, created_by="usr-1")
    job.queue()
    await uow.jobs.save_job(job)
    return asset, job


def _dispatcher(uow, gateway, objects):
    return DispatchIngestionJobHandler(uow, gateway, EventBus(), storage=lambda: objects, bucket=BUCKET)


# --- job creation and reprocess ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unmanaged_asset_cannot_be_queued_or_reprocessed() -> None:
    uow, objects = FakeContentUnitOfWork(), StoredObjects()
    asset, _ = await _setup(uow, objects, manage=False)
    jobs_before = dict(uow.jobs.jobs)

    with pytest.raises(UnmanagedAssetError):
        await CreateIngestionJobHandler(uow, EventBus(), bucket=BUCKET).handle(
            CreateIngestionJobCommand(asset_id=asset.id, tenant_id=TENANT, created_by="usr-1")
        )
    with pytest.raises(UnmanagedAssetError):
        await ReprocessAssetHandler(uow, EventBus(), bucket=BUCKET).handle(
            ReprocessAssetCommand(asset_id=asset.id, tenant_id=TENANT, created_by="usr-1")
        )

    assert uow.jobs.jobs == jobs_before  # no job was created


@pytest.mark.asyncio
async def test_a_managed_asset_is_queued() -> None:
    uow, objects = FakeContentUnitOfWork(), StoredObjects()
    asset, _ = await _setup(uow, objects)

    job = await CreateIngestionJobHandler(uow, EventBus(), bucket=BUCKET).handle(
        CreateIngestionJobCommand(asset_id=asset.id, tenant_id=TENANT, created_by="usr-1")
    )

    assert job.status == IngestionStatus.QUEUED


# --- dispatch ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_verified_object_is_dispatched() -> None:
    uow, objects, gateway = FakeContentUnitOfWork(), StoredObjects(), FakeAIGateway()
    _, job = await _setup(uow, objects)

    result = await _dispatcher(uow, gateway, objects).handle(dispatch_cmd(job.id))

    assert result.status == IngestionStatus.PROCESSING
    assert gateway.dispatched_jobs == [job.id]


def _replace(objects: StoredObjects, asset: ContentAsset, **changes) -> None:
    key = object_key(asset.tenant_id, asset.id, asset.content_sha256)
    info = objects.objects[key]
    objects.objects[key] = ObjectInfo(
        key=key,
        size_bytes=changes.get("size_bytes", info.size_bytes),
        content_type=info.content_type,
        sha256=changes.get("sha256", info.sha256),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "code", "retryable"),
    [
        ("unmanaged", "ASSET_NOT_IN_MANAGED_STORAGE", False),
        ("missing", "ASSET_OBJECT_MISSING", False),
        ("wrong size", "ASSET_OBJECT_MISMATCH", False),
        ("wrong hash", "ASSET_OBJECT_MISMATCH", False),
        ("storage down", "OBJECT_STORAGE_UNAVAILABLE", True),
    ],
)
async def test_an_unverified_object_never_reaches_the_ai_service(case, code, retryable) -> None:
    uow, objects, gateway = FakeContentUnitOfWork(), StoredObjects(), FakeAIGateway()
    asset, job = await _setup(uow, objects, manage=case != "unmanaged")
    if case == "missing":
        objects.objects.clear()
    elif case == "wrong size":
        _replace(objects, asset, size_bytes=asset.file_size_bytes + 1)
    elif case == "wrong hash":
        _replace(objects, asset, sha256="0" * 64)
    elif case == "storage down":
        objects.head_error = ObjectStorageUnavailableError("down")

    result = await _dispatcher(uow, gateway, objects).handle(dispatch_cmd(job.id))

    assert gateway.dispatched_jobs == []  # the AI-service was never contacted
    assert (result.status, result.error_code, result.is_retryable) == (IngestionStatus.FAILED, code, retryable)
    assert uow.jobs.jobs[job.id].status == IngestionStatus.FAILED
    assert asset.ingestion_status == IngestionStatus.FAILED


@pytest.mark.asyncio
async def test_an_object_whose_storage_reports_no_hash_is_checked_by_size() -> None:
    """Some stores do not report SHA-256 on head; size must still match,
    and PR 4 verifies the bytes on fetch."""
    uow, objects, gateway = FakeContentUnitOfWork(), StoredObjects(), FakeAIGateway()
    asset, job = await _setup(uow, objects)
    _replace(objects, asset, sha256=None)

    result = await _dispatcher(uow, gateway, objects).handle(dispatch_cmd(job.id))

    assert result.status == IngestionStatus.PROCESSING

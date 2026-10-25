"""Version by upload as a state transition (P3-1 PR 3b, design section 9),
on the real schema with an in-memory store and fault injection."""

import uuid
from contextlib import asynccontextmanager

import pytest

from app.application.content.access import ContentNotFoundError, PlatformContentNotWritableError
from app.application.content.upload import (
    AssetNotVersionableError,
    AssetVersionConflictError,
    ContentAssetUploadService,
    DuplicateContentError,
    IdempotencyKeyReusedError,
    UploadStorageUnavailableError,
    derive_version_id,
    managed_storage_key,
    object_key,
)
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, VisibilityScope
from app.domain.content.storage import ObjectStorageUnavailableError
from tests.integration.content.test_content_upload_service import OTHER_PDF, PDF, FakeStorage, _source, body_of

BUCKET = "build-documents"
THIRD_PDF = b"%PDF-1.7\n" + b"third edition " * 200


@pytest.fixture
def tenant_id() -> str:
    return f"tenant-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


def _service(uow_factory, storage) -> ContentAssetUploadService:
    return ContentAssetUploadService(uow_factory=uow_factory, storage_factory=lambda: storage, bucket=lambda: BUCKET)


async def _parent(service, uow_factory, tenant_id, data=PDF):
    source = await _source(uow_factory, tenant_id=tenant_id)
    result = await service.upload(
        source_id=source.id,
        tenant_id=tenant_id,
        user_id="usr-1",
        user_email="usr-1@build.internal",
        file_name="notes.pdf",
        idempotency_key=f"k-{uuid.uuid4().hex}",
        body=body_of(data),
    )
    return result.asset


async def _version(service, parent_id, tenant_id, data=OTHER_PDF, key="v-1"):
    return await service.upload_version(
        parent_asset_id=parent_id,
        tenant_id=tenant_id,
        user_id="usr-2",
        user_email="usr-2@build.internal",
        file_name="notes-v2.pdf",
        idempotency_key=key,
        body=body_of(data),
        correlation_id="corr-v",
    )


async def _rows(uow_factory, source_id) -> list[ContentAsset]:
    async with uow_factory() as uow:
        assets, _ = await uow.assets.list_assets_by_source(source_id)
    return assets


async def _get(uow_factory, asset_id) -> ContentAsset:
    async with uow_factory() as uow:
        return await uow.assets.get_asset_by_id(asset_id)


# --- the transition --------------------------------------------------------------------------


async def test_a_version_supersedes_its_parent_and_is_linked_to_it(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)

    result = await _version(service, parent.id, tenant_id)

    child = result.asset
    assert result.created
    assert (child.parent_asset_id, child.source_id, child.tenant_id) == (parent.id, parent.source_id, tenant_id)
    assert (child.asset_version, child.status) == (parent.asset_version + 1, AssetStatus.ACTIVE)
    assert child.id == derive_version_id(tenant_id, parent.id, "v-1")
    assert managed_storage_key(child, BUCKET) in storage.objects
    assert (await _get(uow_factory, parent.id)).status == AssetStatus.SUPERSEDED
    current = [a for a in await _rows(uow_factory, parent.source_id) if a.status == AssetStatus.ACTIVE]
    assert [a.id for a in current] == [child.id]


async def test_a_retry_returns_the_same_version_and_never_supersedes_twice(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)

    first = await _version(service, parent.id, tenant_id, key="v-retry")
    retry = await _version(service, parent.id, tenant_id, key="v-retry")

    assert (first.created, retry.created) == (True, False)
    assert retry.asset.id == first.asset.id
    assert len(await _rows(uow_factory, parent.source_id)) == 2  # the parent and one child


async def test_the_same_key_with_other_bytes_is_key_reuse(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    await _version(service, parent.id, tenant_id, key="v-k")

    with pytest.raises(IdempotencyKeyReusedError):
        await _version(service, parent.id, tenant_id, data=THIRD_PDF, key="v-k")


async def test_a_superseded_asset_cannot_be_versioned_again(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    await _version(service, parent.id, tenant_id, key="v-first")
    puts = storage.puts

    with pytest.raises(AssetVersionConflictError):
        await _version(service, parent.id, tenant_id, data=THIRD_PDF, key="v-second")

    assert storage.puts == puts  # refused before storing


@pytest.mark.parametrize("which", ["the parent's own bytes", "another asset's bytes"])
async def test_duplicate_content_is_refused_and_the_parent_stays_current(uow_factory, storage, tenant_id, which):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    other = await _parent(service, uow_factory, tenant_id, data=THIRD_PDF)
    data = PDF if which == "the parent's own bytes" else THIRD_PDF

    with pytest.raises(DuplicateContentError) as caught:
        await _version(service, parent.id, tenant_id, data=data)

    assert caught.value.existing_asset_id == (parent.id if data == PDF else other.id)
    assert (await _get(uow_factory, parent.id)).status == AssetStatus.ACTIVE


async def test_a_revoked_asset_is_not_versionable(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    async with uow_factory() as uow:
        row = await uow.assets.get_asset_by_id(parent.id)
        row.revoke("withdrawn")
        await uow.assets.save_asset(row)

    with pytest.raises(AssetNotVersionableError):
        await _version(service, parent.id, tenant_id)


async def test_another_tenants_or_a_platform_asset_cannot_be_versioned(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    platform_source = await _source(uow_factory, visibility=VisibilityScope.PLATFORM)
    platform = ContentAsset.create(
        source_id=platform_source.id,
        tenant_id=None,
        file_name="p.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        content_sha256="ab" * 32,
        storage_uri="s3://x/p",
        created_by="system",
        created_by_email="system@build.internal",
    )
    async with uow_factory() as uow:
        await uow.assets.insert_asset(platform)

    with pytest.raises(ContentNotFoundError):
        await _version(service, parent.id, "tenant-other")
    with pytest.raises(PlatformContentNotWritableError):
        await _version(service, platform.id, tenant_id)
    with pytest.raises(ContentNotFoundError):
        await _version(service, str(uuid.uuid4()), tenant_id)
    assert (await _get(uow_factory, parent.id)).status == AssetStatus.ACTIVE
    assert storage.puts == 1  # only the parent's upload


# --- failures leave the parent current ---------------------------------------------------------


async def test_storage_failure_leaves_the_parent_current(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    storage.put_error = ObjectStorageUnavailableError("down")

    with pytest.raises(UploadStorageUnavailableError):
        await _version(service, parent.id, tenant_id)

    assert (await _get(uow_factory, parent.id)).status == AssetStatus.ACTIVE


async def test_a_failed_insert_rolls_the_supersede_back_and_removes_the_object(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)

    @asynccontextmanager
    async def failing_insert():
        async with uow_factory() as uow:

            async def fail(_asset):
                raise RuntimeError("database went away")

            uow.assets.insert_asset = fail
            yield uow

    failing = ContentAssetUploadService(uow_factory=failing_insert, storage_factory=lambda: storage, bucket=lambda: BUCKET)

    with pytest.raises(RuntimeError):
        await _version(failing, parent.id, tenant_id)

    assert (await _get(uow_factory, parent.id)).status == AssetStatus.ACTIVE  # supersede rolled back
    child_key = object_key(tenant_id, derive_version_id(tenant_id, parent.id, "v-1"), body_of(OTHER_PDF).sha256)
    assert child_key not in storage.objects  # compensated
    assert len(await _rows(uow_factory, parent.source_id)) == 1


# --- races (simulated: the winner commits while the loser stores) -------------------------------


async def test_a_concurrent_version_of_the_same_parent_loses_cleanly(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    winner_service = _service(uow_factory, FakeStorage())
    holder = {}

    async def concurrent_winner(_key):
        storage.on_put = None
        holder["winner"] = await _version(winner_service, parent.id, tenant_id, data=THIRD_PDF, key="v-winner")

    storage.on_put = concurrent_winner

    with pytest.raises(AssetVersionConflictError):
        await _version(service, parent.id, tenant_id, key="v-loser")

    loser_key = object_key(tenant_id, derive_version_id(tenant_id, parent.id, "v-loser"), body_of(OTHER_PDF).sha256)
    assert loser_key not in storage.objects  # the loser left no object
    active = [a for a in await _rows(uow_factory, parent.source_id) if a.status == AssetStatus.ACTIVE]
    assert [a.id for a in active] == [holder["winner"].asset.id]  # exactly one current version


async def test_a_concurrent_retry_of_the_same_request_is_a_replay(uow_factory, storage, tenant_id):
    service = _service(uow_factory, storage)
    parent = await _parent(service, uow_factory, tenant_id)
    twin = _service(uow_factory, FakeStorage())

    async def same_request_wins(_key):
        storage.on_put = None
        await _version(twin, parent.id, tenant_id, key="v-same")

    storage.on_put = same_request_wins

    result = await _version(service, parent.id, tenant_id, key="v-same")

    assert result.created is False
    assert managed_storage_key(result.asset, BUCKET) in storage.objects  # the shared object was kept
    assert len(await _rows(uow_factory, parent.source_id)) == 2

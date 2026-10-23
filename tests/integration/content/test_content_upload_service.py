"""ContentAssetUploadService against the real schema (SQLite) and an
in-memory object store with fault injection. Each test maps to a row of the
idempotency contract or a rule of docs/p3-1-pr2-upload-design.md."""

import hashlib
import io
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.application.content.upload import (
    SIGNATURE_BYTES,
    ContentAssetUploadService,
    DuplicateContentError,
    IdempotencyKeyReusedError,
    InvalidUploadRequestError,
    PlatformSourceUploadNotSupportedError,
    UnsupportedUploadTypeError,
    UploadedBody,
    UploadSourceNotFoundError,
    UploadSourceRevokedError,
    UploadStorageUnavailableError,
    derive_asset_id,
    object_key,
)
from app.core.metrics import content_upload_orphaned_objects_total
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AuthorityLevel, ContentSourceType, VisibilityScope
from app.domain.content.source import ContentSource
from app.domain.content.storage import (
    ObjectInfo,
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorageUnavailableError,
    StoredObject,
)
from app.infrastructure.content.unit_of_work import ContentUnitOfWork

BUCKET = "build-documents"
TENANT = "tenant-a"  # replaced per test by the tenant fixture
PDF = b"%PDF-1.7\n" + b"lecture notes " * 200
OTHER_PDF = b"%PDF-1.7\n" + b"different notes " * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def body_of(data: bytes) -> UploadedBody:
    return UploadedBody(
        file=io.BytesIO(data),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        head=data[:SIGNATURE_BYTES],
    )


class FakeStorage:
    """ObjectStorage in memory, with the failures the service must handle."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.on_put = None
        self.puts = 0

    async def put(self, key, data, *, content_type, expected_sha256=None):
        if self.put_error is not None:
            raise self.put_error
        raw = data.read() if hasattr(data, "read") else bytes(data)
        sha = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and expected_sha256 != sha:
            raise ObjectIntegrityError("mismatch")
        self.objects[key] = raw
        self.puts += 1
        if self.on_put is not None:
            await self.on_put(key)
        return StoredObject(key=key, size_bytes=len(raw), sha256=sha, content_type=content_type)

    async def get(self, key, *, expected_sha256, max_bytes):
        if key not in self.objects:
            raise ObjectNotFoundError("missing")
        return self.objects[key]

    async def head(self, key):
        if key not in self.objects:
            raise ObjectNotFoundError("missing")
        raw = self.objects[key]
        return ObjectInfo(key=key, size_bytes=len(raw), content_type=None, sha256=hashlib.sha256(raw).hexdigest())

    async def delete(self, key):
        if self.delete_error is not None:
            raise self.delete_error
        self.objects.pop(key, None)


@pytest.fixture
def uow_factory(engine: AsyncEngine):
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    @asynccontextmanager
    async def factory() -> AsyncIterator[ContentUnitOfWork]:
        async with maker() as session:
            async with ContentUnitOfWork(session) as uow:
                yield uow

    return factory


async def _source(uow_factory, *, tenant_id=None, visibility=VisibilityScope.TENANT, revoked=False):
    source = ContentSource.create(
        code=f"SRC_{uuid.uuid4().hex[:8].upper()}",
        name="MTS 102 notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.REGULATORY if visibility == VisibilityScope.PLATFORM else AuthorityLevel.INSTITUTIONAL,
        visibility=visibility,
        created_by="usr-1",
        created_by_email="usr-1@build.internal",
        tenant_id=None if visibility == VisibilityScope.PLATFORM else (tenant_id or TENANT),
    )
    if revoked:
        source.revoke("withdrawn")
    async with uow_factory() as uow:
        await uow.sources.save_source(source)
    return source


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture(autouse=True)
def tenant(monkeypatch):
    """Each test in its own tenant: uq_content_assets_tenant_hash is
    tenant-wide and the schema is shared by the whole session."""
    value = f"tenant-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(sys.modules[__name__], "TENANT", value)
    return value


@pytest.fixture
def service(uow_factory, storage):
    return ContentAssetUploadService(uow_factory=uow_factory, storage_factory=lambda: storage, bucket=lambda: BUCKET)


async def _upload(service, source, data=PDF, *, key=None, name="notes.pdf", tenant_id=None):
    return await service.upload(
        source_id=source.id,
        tenant_id=tenant_id or TENANT,
        user_id="usr-1",
        user_email="usr-1@build.internal",
        file_name=name,
        idempotency_key=key or f"key-{uuid.uuid4().hex}",
        body=body_of(data),
        correlation_id="corr-1",
    )


# --- the idempotency contract ---------------------------------------------------------------


async def test_a_new_key_stores_the_object_and_creates_the_asset(service, storage, uow_factory):
    source = await _source(uow_factory)

    result = await _upload(service, source, key="k-new")

    sha = hashlib.sha256(PDF).hexdigest()
    asset = result.asset
    assert result.created is True
    assert asset.id == derive_asset_id(TENANT, source.id, "k-new")
    assert (asset.file_size_bytes, asset.content_sha256, asset.mime_type) == (len(PDF), sha, "application/pdf")
    assert asset.storage_uri == f"s3://{BUCKET}/tenants/{TENANT}/assets/{asset.id}/{sha}"
    assert storage.objects == {object_key(TENANT, asset.id, sha): PDF}


async def test_the_same_key_and_bytes_return_the_original_asset(service, storage, uow_factory):
    source = await _source(uow_factory)
    first = await _upload(service, source, key="k-retry")

    second = await _upload(service, source, key="k-retry")

    assert (second.created, second.asset.id) == (False, first.asset.id)
    assert storage.puts == 1


async def test_the_same_key_with_different_bytes_is_a_conflict_and_stores_nothing(service, storage, uow_factory):
    source = await _source(uow_factory)
    await _upload(service, source, key="k-reused")

    with pytest.raises(IdempotencyKeyReusedError) as caught:
        await _upload(service, source, OTHER_PDF, key="k-reused")

    assert (caught.value.status_code, caught.value.code) == (409, "IDEMPOTENCY_KEY_REUSED")
    assert storage.puts == 1


async def test_the_same_key_on_another_source_is_an_independent_asset(service, uow_factory):
    first_source = await _source(uow_factory)
    second_source = await _source(uow_factory)

    a = await _upload(service, first_source, key="k-shared")
    b = await _upload(service, second_source, OTHER_PDF, key="k-shared")

    assert a.asset.id != b.asset.id
    assert (a.asset.source_id, b.asset.source_id) == (first_source.id, second_source.id)


async def test_a_replay_heals_a_missing_object_from_the_identical_bytes(service, storage, uow_factory):
    source = await _source(uow_factory)
    first = await _upload(service, source, key="k-heal")
    storage.objects.clear()

    replay = await _upload(service, source, key="k-heal")

    sha = hashlib.sha256(PDF).hexdigest()
    assert replay.created is False
    assert storage.objects == {object_key(TENANT, first.asset.id, sha): PDF}


async def test_identical_bytes_under_a_new_key_are_duplicate_content(service, storage, uow_factory):
    source = await _source(uow_factory)
    first = await _upload(service, source, key="k-one")

    with pytest.raises(DuplicateContentError) as caught:
        await _upload(service, source, key="k-two")

    assert (caught.value.status_code, caught.value.code) == (409, "DUPLICATE_CONTENT")
    assert caught.value.existing_asset_id == first.asset.id
    assert storage.puts == 1  # refused before anything was stored


async def test_duplicate_content_is_tenant_wide_across_sources(service, storage, uow_factory):
    first_source = await _source(uow_factory)
    second_source = await _source(uow_factory)
    first = await _upload(service, first_source, key="k-a")

    with pytest.raises(DuplicateContentError) as caught:
        await _upload(service, second_source, key="k-b")

    assert caught.value.existing_asset_id == first.asset.id
    assert storage.puts == 1


async def test_the_same_bytes_in_another_tenant_are_not_a_duplicate(service, uow_factory):
    source = await _source(uow_factory)
    other = await _source(uow_factory, tenant_id=f"{TENANT}-other")
    await _upload(service, source, key="k-1")

    result = await _upload(service, other, key="k-1", tenant_id=f"{TENANT}-other")

    assert result.created is True


async def test_a_retry_of_the_original_key_is_not_a_duplicate(service, uow_factory):
    source = await _source(uow_factory)
    first = await _upload(service, source, key="k-orig")

    again = await _upload(service, source, key="k-orig")

    assert (again.created, again.asset.id) == (False, first.asset.id)


# --- concurrency: the primary key decides --------------------------------------------------


async def _commit_winner(uow_factory, source, key, data):
    sha = hashlib.sha256(data).hexdigest()
    asset_id = derive_asset_id(TENANT, source.id, key)
    winner = ContentAsset.create(
        source_id=source.id,
        tenant_id=TENANT,
        file_name="notes.pdf",
        mime_type="application/pdf",
        file_size_bytes=len(data),
        content_sha256=sha,
        storage_uri=f"s3://{BUCKET}/{object_key(TENANT, asset_id, sha)}",
        created_by="usr-2",
        created_by_email="usr-2@build.internal",
        asset_id=asset_id,
    )
    async with uow_factory() as uow:
        await uow.assets.save_asset(winner)
    return winner


async def test_a_concurrent_request_with_the_same_key_and_bytes_yields_one_asset(service, storage, uow_factory):
    source = await _source(uow_factory)

    async def concurrent_winner(_key):
        await _commit_winner(uow_factory, source, "k-race", PDF)

    storage.on_put = concurrent_winner  # the winner commits while we store

    result = await _upload(service, source, key="k-race")

    assert result.created is False
    assert result.asset.created_by == "usr-2"
    assert len(storage.objects) == 1  # the shared object was not compensated away


async def test_a_concurrent_request_with_the_same_key_and_other_bytes_is_a_conflict(service, storage, uow_factory):
    source = await _source(uow_factory)

    async def concurrent_winner(_key):
        await _commit_winner(uow_factory, source, "k-race-2", OTHER_PDF)

    storage.on_put = concurrent_winner

    with pytest.raises(IdempotencyKeyReusedError):
        await _upload(service, source, key="k-race-2")

    assert storage.objects == {}  # our object, under its own SHA-256 key, was deleted


async def test_a_concurrent_duplicate_under_another_key_is_duplicate_content(service, storage, uow_factory):
    source = await _source(uow_factory)
    holder = {}

    async def concurrent_other_key(_key):
        holder["winner"] = await _commit_winner(uow_factory, source, "k-someone-else", PDF)

    storage.on_put = concurrent_other_key  # same bytes committed under another key

    with pytest.raises(DuplicateContentError) as caught:
        await _upload(service, source, key="k-mine")

    assert caught.value.existing_asset_id == holder["winner"].id
    sha = hashlib.sha256(PDF).hexdigest()
    mine = object_key(TENANT, derive_asset_id(TENANT, source.id, "k-mine"), sha)
    assert mine not in storage.objects  # our object was compensated: no orphan


# --- compensation ---------------------------------------------------------------------------


@pytest.fixture
def failing_insert_factory(uow_factory):
    """Units of work whose asset insert fails; reads work as usual."""

    @asynccontextmanager
    async def factory():
        async with uow_factory() as uow:

            async def fail(_asset):
                raise RuntimeError("database went away")

            uow.assets.insert_asset = fail
            yield uow

    return factory


async def test_a_failed_commit_deletes_the_stored_object(uow_factory, failing_insert_factory, storage):
    source = await _source(uow_factory)
    service = ContentAssetUploadService(
        uow_factory=failing_insert_factory, storage_factory=lambda: storage, bucket=lambda: BUCKET
    )

    with pytest.raises(RuntimeError):
        await _upload(service, source, key="k-commit-fails")

    assert storage.puts == 1
    assert storage.objects == {}  # stored, then compensated


async def test_a_failed_compensation_is_logged_and_counted(uow_factory, failing_insert_factory, storage):
    source = await _source(uow_factory)
    storage.delete_error = ObjectStorageUnavailableError("storage down")
    service = ContentAssetUploadService(
        uow_factory=failing_insert_factory, storage_factory=lambda: storage, bucket=lambda: BUCKET
    )
    counter = content_upload_orphaned_objects_total.labels(reason="commit_failed")
    before = counter._value.get()

    with structlog.testing.capture_logs() as logs, pytest.raises(RuntimeError):
        await _upload(service, source, key="k-orphan")

    assert counter._value.get() == before + 1
    entry = next(e for e in logs if e["event"] == "upload_compensation_failed")
    expected_id = derive_asset_id(TENANT, source.id, "k-orphan")
    assert (entry["asset_id"], entry["correlation_id"], entry["reason"]) == (expected_id, "corr-1", "commit_failed")
    assert entry["error_code"] == "OBJECT_STORAGE_UNAVAILABLE"
    assert PDF.decode() not in repr(entry)
    assert len(storage.objects) == 1  # the orphan the metric reports


async def test_storage_unavailable_is_a_retryable_503_and_creates_no_asset(service, storage, uow_factory):
    source = await _source(uow_factory)
    storage.put_error = ObjectStorageUnavailableError("down")

    with pytest.raises(UploadStorageUnavailableError) as caught:
        await _upload(service, source, key="k-down")

    assert caught.value.status_code == 503
    async with uow_factory() as uow:
        assert await uow.assets.get_asset_by_id(derive_asset_id(TENANT, source.id, "k-down")) is None


# --- scope and validation -------------------------------------------------------------------


async def test_a_missing_source_and_another_tenants_source_are_both_404(service, uow_factory):
    other_tenant_source = await _source(uow_factory, tenant_id=f"{TENANT}-other")
    missing = ContentSource.create(
        code="SRC_MISSING",
        name="never saved",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-1",
        created_by_email="usr-1@build.internal",
        tenant_id=TENANT,
    )

    for source in (missing, other_tenant_source):
        with pytest.raises(UploadSourceNotFoundError) as caught:
            await _upload(service, source)
        assert (caught.value.status_code, str(caught.value)) == (404, "no such source")


async def test_platform_sources_and_revoked_sources_are_refused(service, uow_factory):
    platform = await _source(uow_factory, visibility=VisibilityScope.PLATFORM)
    revoked = await _source(uow_factory, revoked=True)

    with pytest.raises(PlatformSourceUploadNotSupportedError):
        await _upload(service, platform)
    with pytest.raises(UploadSourceRevokedError) as caught:
        await _upload(service, revoked)
    assert caught.value.status_code == 409


@pytest.mark.parametrize("key", [None, "", "has space", "k" * 129, "slash/no"])
async def test_an_invalid_idempotency_key_is_400(service, uow_factory, key):
    source = await _source(uow_factory)

    with pytest.raises(InvalidUploadRequestError) as caught:
        await service.upload(
            source_id=source.id,
            tenant_id=TENANT,
            user_id="usr-1",
            user_email="usr-1@build.internal",
            file_name="notes.pdf",
            idempotency_key=key,
            body=body_of(PDF),
        )
    assert (caught.value.status_code, caught.value.code) == (400, "INVALID_IDEMPOTENCY_KEY")


@pytest.mark.parametrize("name", [None, "", "../etc/passwd", "a\\b.pdf", "tab\t.pdf", "x" * 252 + ".pdf"])
async def test_an_invalid_file_name_is_400(service, uow_factory, name):
    source = await _source(uow_factory)

    with pytest.raises(InvalidUploadRequestError) as caught:
        await _upload(service, source, name=name)
    assert caught.value.code == "INVALID_FILE_NAME"


async def test_an_empty_upload_is_400(service, uow_factory):
    source = await _source(uow_factory)

    with pytest.raises(InvalidUploadRequestError) as caught:
        await _upload(service, source, b"")
    assert caught.value.code == "EMPTY_UPLOAD"


@pytest.mark.parametrize(
    ("data", "name", "mime_type"),
    [
        (PDF, "a.pdf", "application/pdf"),
        (PNG, "a.png", "image/png"),
        (JPEG, "a.jpg", "image/jpeg"),
        (JPEG, "A.JPEG", "image/jpeg"),
    ],
)
async def test_the_type_comes_from_the_bytes(service, uow_factory, data, name, mime_type):
    source = await _source(uow_factory)

    result = await _upload(service, source, data, name=name)

    assert result.asset.mime_type == mime_type


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"<html>not a pdf</html>", "notes.pdf"),  # unknown signature
        (PDF, "notes.png"),  # extension disagrees
        (PNG, "photo.pdf"),
        (PDF, "notes"),  # no extension
        (b"PK\x03\x04 docx", "notes.docx"),  # not on the allow-list
    ],
)
async def test_unknown_or_mismatched_types_are_415(service, storage, uow_factory, data, name):
    source = await _source(uow_factory)

    with pytest.raises(UnsupportedUploadTypeError) as caught:
        await _upload(service, source, data, name=name)
    assert caught.value.status_code == 415
    assert storage.puts == 0

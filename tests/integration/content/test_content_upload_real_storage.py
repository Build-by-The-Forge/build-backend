"""ContentAssetUploadService with the real S3ObjectStorage (SeaweedFS in the
storage gate): the object is stored and read back by its SHA-256, a replay
keeps it, key reuse and duplicate content store nothing, and an upload
interrupted between the object and the row is recovered by its retry.

Configuration and the required/skip rule come from
tests/infrastructure/content/test_s3_object_storage_real.py.
"""

import hashlib
import uuid

import pytest

from app.application.content.upload import (
    ContentAssetUploadService,
    DuplicateContentError,
    IdempotencyKeyReusedError,
    derive_asset_id,
    object_key,
)
from app.domain.content.storage import ObjectNotFoundError
from tests.infrastructure.content.test_s3_object_storage_real import CONFIG, CONFIGURED, _storage
from tests.integration.content.test_content_upload_service import OTHER_PDF, PDF, _source, _upload

pytestmark = pytest.mark.skipif(not CONFIGURED, reason="OBJECT_STORAGE_TEST_* not set")


@pytest.fixture
def tenant_id():
    return f"tenant-{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def storage():
    """The real bucket; every object a test stored is removed afterwards."""
    real = _storage("WRITER_A", "BUCKET_A")
    stored: list[str] = []
    put = real.put

    async def tracking_put(key, data, **kwargs):
        stored.append(key)
        return await put(key, data, **kwargs)

    real.put = tracking_put
    yield real
    for key in stored:
        await real.delete(key)


@pytest.fixture
def service(uow_factory, storage):
    return ContentAssetUploadService(uow_factory=uow_factory, storage_factory=lambda: storage, bucket=lambda: CONFIG["BUCKET_A"])


def _key_of(storage_uri: str) -> str:
    return storage_uri.split("/", 3)[3]


async def test_an_upload_is_stored_and_read_back_by_its_sha256_and_a_replay_keeps_it(service, storage, uow_factory, tenant_id):
    source = await _source(uow_factory, tenant_id=tenant_id)

    created = await _upload(service, source, PDF, key="k-real", tenant_id=tenant_id)
    replayed = await _upload(service, source, PDF, key="k-real", tenant_id=tenant_id)

    sha = hashlib.sha256(PDF).hexdigest()
    assert created.created and not replayed.created and replayed.asset.id == created.asset.id
    assert created.asset.storage_uri == f"s3://{CONFIG['BUCKET_A']}/{object_key(tenant_id, created.asset.id, sha)}"
    assert await storage.get(_key_of(created.asset.storage_uri), expected_sha256=sha, max_bytes=len(PDF)) == PDF


async def test_key_reuse_and_duplicate_content_store_nothing(service, storage, uow_factory, tenant_id):
    source = await _source(uow_factory, tenant_id=tenant_id)
    await _upload(service, source, PDF, key="k-first", tenant_id=tenant_id)

    with pytest.raises(IdempotencyKeyReusedError):
        await _upload(service, source, OTHER_PDF, key="k-first", tenant_id=tenant_id)
    with pytest.raises(DuplicateContentError):
        await _upload(service, source, PDF, key="k-second", tenant_id=tenant_id)

    reused = object_key(tenant_id, derive_asset_id(tenant_id, source.id, "k-first"), hashlib.sha256(OTHER_PDF).hexdigest())
    duplicate = object_key(tenant_id, derive_asset_id(tenant_id, source.id, "k-second"), hashlib.sha256(PDF).hexdigest())
    for key in (reused, duplicate):
        with pytest.raises(ObjectNotFoundError):
            await storage.head(key)


async def test_an_upload_interrupted_after_the_object_is_recovered_by_its_retry(service, storage, uow_factory, tenant_id):
    """The process stored the object and died before the commit: the
    retry with the same key and bytes re-stores the same key and commits."""
    source = await _source(uow_factory, tenant_id=tenant_id)
    sha = hashlib.sha256(PDF).hexdigest()
    key = object_key(tenant_id, derive_asset_id(tenant_id, source.id, "k-crash"), sha)
    await storage.put(key, PDF, content_type="application/pdf", expected_sha256=sha)  # no row follows

    result = await _upload(service, source, PDF, key="k-crash", tenant_id=tenant_id)

    assert result.created
    assert _key_of(result.asset.storage_uri) == key
    assert await storage.get(key, expected_sha256=sha, max_bytes=len(PDF)) == PDF

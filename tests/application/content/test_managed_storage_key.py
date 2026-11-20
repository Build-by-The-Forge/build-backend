"""managed_storage_key: only the exact server-written reference for a row
is trusted (P3-1 PR 3b, design section 10)."""

import hashlib

import pytest

from app.application.content.upload import managed_storage_key, object_key, resolve_managed_key, storage_uri_for
from app.domain.content.asset import ContentAsset
from app.domain.content.blob import ContentBlob

BUCKET = "build-documents"
TENANT = "tenant-a"
SHA = hashlib.sha256(b"notes").hexdigest()


def asset_with(storage_uri: str | None = None, *, tenant_id: str | None = TENANT, asset_id: str = "asset-1") -> ContentAsset:
    uri = storage_uri or storage_uri_for(BUCKET, object_key(tenant_id or "none", asset_id, SHA))
    return ContentAsset.create(
        source_id="source-1",
        tenant_id=tenant_id,
        file_name="notes.pdf",
        mime_type="application/pdf",
        file_size_bytes=5,
        content_sha256=SHA,
        storage_uri=uri,
        created_by="usr-1",
        created_by_email="usr-1@build.internal",
        asset_id=asset_id,
    )


def test_the_server_written_reference_is_managed() -> None:
    asset = asset_with()

    assert managed_storage_key(asset, BUCKET) == f"tenants/{TENANT}/assets/asset-1/{SHA}"


@pytest.mark.parametrize(
    "uri",
    [
        f"s3://other-bucket/tenants/{TENANT}/assets/asset-1/{SHA}",  # foreign bucket
        f"s3://{BUCKET}/tenants/tenant-b/assets/asset-1/{SHA}",  # another tenant's prefix
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-2/{SHA}",  # another asset's object
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{'0' * 64}",  # other bytes
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{SHA}/extra",  # extra segment
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{SHA}/",  # trailing slash
        f"s3://{BUCKET}//tenants/{TENANT}/assets/asset-1/{SHA}",  # doubled slash
        f"s3://{BUCKET}/tenants/{TENANT}/assets/x/../asset-1/{SHA}",  # dot segments
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{SHA.upper()}",  # case change
        f"S3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{SHA}",  # scheme case
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset%2D1/{SHA}",  # percent-encoding
        f"https://{BUCKET}.example/tenants/{TENANT}/assets/asset-1/{SHA}",  # another scheme
        f"tenants/{TENANT}/assets/asset-1/{SHA}",  # a bare key
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{SHA} ",  # whitespace
    ],
)
def test_any_other_reference_is_not_managed(uri: str) -> None:
    asset = asset_with()
    asset.storage_uri = uri  # a legacy or client-supplied value, as stored

    assert managed_storage_key(asset, BUCKET) is None


def test_a_platform_row_is_never_managed() -> None:
    asset = asset_with(tenant_id=None)

    assert managed_storage_key(asset, BUCKET) is None


def test_an_unconfigured_bucket_trusts_nothing() -> None:
    assert managed_storage_key(asset_with(), "") is None


# --- M3-D PR 7: the blob form -----------------------------------------------------------

GENERATION = "3f2c1b0a-9d8e-4c7b-a6f5-e4d3c2b1a098"
BLOB_KEY = f"tenants/{TENANT}/blobs/{SHA}/{GENERATION}"


def blob(**overrides) -> ContentBlob:
    fields = {
        "id": "blob-1",
        "tenant_id": TENANT,
        "content_sha256": SHA,
        "generation": GENERATION,
        "object_key": BLOB_KEY,
        "state": "active",
    } | overrides
    return ContentBlob(**fields)


def blob_asset(uri: str = f"s3://{BUCKET}/{BLOB_KEY}", blob_id: str | None = "blob-1") -> ContentAsset:
    asset = asset_with()
    asset.storage_uri = uri  # as stored: creation would strip it
    asset.blob_id = blob_id
    return asset


def test_a_document_in_its_active_blob_is_managed() -> None:
    assert managed_storage_key(blob_asset(), BUCKET, blob()) == BLOB_KEY


@pytest.mark.parametrize(
    "row",
    [
        None,  # the row couldn't be read
        blob(id="blob-2"),  # another blob than the document names
        blob(tenant_id="tenant-b"),
        blob(content_sha256="0" * 64),
        blob(state="pending"),
        blob(state="deleting"),
        blob(generation=GENERATION.upper(), object_key=f"tenants/{TENANT}/blobs/{SHA}/{GENERATION.upper()}"),
        blob(generation="g1", object_key=f"tenants/{TENANT}/blobs/{SHA}/g1"),
        blob(generation="../x", object_key=f"tenants/{TENANT}/blobs/{SHA}/../x"),
        blob(object_key=f"tenants/{TENANT}/blobs/{SHA}/11111111-2222-4333-8444-555555555555"),  # its key isn't its generation's
        blob(object_key=f"tenants/{TENANT}/assets/asset-1/{SHA}"),
    ],
)
def test_a_blob_document_without_its_own_active_row_is_not_managed(row) -> None:
    assert managed_storage_key(blob_asset(), BUCKET, row) is None


@pytest.mark.parametrize(
    "uri",
    [
        f"s3://other-bucket/{BLOB_KEY}",
        f"s3://{BUCKET}/tenants/tenant-b/blobs/{SHA}/{GENERATION}",
        f"s3://{BUCKET}/tenants/{TENANT}/blobs/{'0' * 64}/{GENERATION}",
        f"s3://{BUCKET}/tenants/{TENANT}/blobs/{SHA}/11111111-2222-4333-8444-555555555555",  # another generation
        f"s3://{BUCKET}/{BLOB_KEY}/",
        f"s3://{BUCKET}/{BLOB_KEY} ",
        f"S3://{BUCKET}/{BLOB_KEY}",
        f"s3://{BUCKET}/tenants/{TENANT}/assets/asset-1/{SHA}",  # its per-document form
        BLOB_KEY,
    ],
)
def test_a_blob_document_whose_uri_isnt_exactly_its_blob_is_not_managed(uri: str) -> None:
    assert managed_storage_key(blob_asset(uri), BUCKET, blob()) is None


def test_a_per_document_row_never_matches_a_blob() -> None:
    asset = asset_with()  # blob_id None, its own object
    assert managed_storage_key(asset, BUCKET, blob()) is None
    asset.storage_uri = f"s3://{BUCKET}/{BLOB_KEY}"
    assert managed_storage_key(asset, BUCKET) is None
    assert managed_storage_key(asset, BUCKET, blob()) is None


def test_a_blob_document_needs_a_tenant_and_a_bucket() -> None:
    assert managed_storage_key(blob_asset(), "", blob()) is None
    platform = blob_asset()
    platform.tenant_id = None
    assert managed_storage_key(platform, BUCKET, blob()) is None


class Blobs:
    def __init__(self, *rows: ContentBlob) -> None:
        self.rows = {(row.tenant_id, row.id): row for row in rows}
        self.calls: list[tuple[str, str]] = []

    async def get(self, tenant_id: str, blob_id: str) -> ContentBlob | None:
        self.calls.append((tenant_id, blob_id))
        return self.rows.get((tenant_id, blob_id))


class Uow:
    def __init__(self, blobs: Blobs | None) -> None:
        if blobs is not None:
            self.blobs = blobs


@pytest.mark.asyncio
async def test_the_blob_is_read_for_the_documents_own_tenant() -> None:
    blobs = Blobs(blob(), blob(tenant_id="tenant-b"))
    assert await resolve_managed_key(Uow(blobs), blob_asset(), BUCKET) == BLOB_KEY
    assert blobs.calls == [(TENANT, "blob-1")]


@pytest.mark.asyncio
async def test_without_a_blob_repository_a_blob_document_is_not_managed() -> None:
    assert await resolve_managed_key(Uow(None), blob_asset(), BUCKET) is None


@pytest.mark.asyncio
async def test_a_per_document_row_needs_no_blob_repository() -> None:
    expected = f"tenants/{TENANT}/assets/asset-1/{SHA}"
    assert await resolve_managed_key(Uow(None), asset_with(), BUCKET) == expected

"""managed_storage_key: only the exact server-written reference for a row
is trusted (P3-1 PR 3b, design section 10)."""

import hashlib

import pytest

from app.application.content.upload import managed_storage_key, object_key, storage_uri_for
from app.domain.content.asset import ContentAsset

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

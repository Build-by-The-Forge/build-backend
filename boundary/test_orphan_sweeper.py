"""The orphan sweeper against PostgreSQL and the real S3-compatible store."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.content.storage import ObjectNotFoundError
from app.infrastructure.content.orphan_sweeper import sweep_orphaned_objects
from app.infrastructure.content.s3_object_storage import S3ObjectStorage
from boundary.conftest import create_asset, object_store

BUCKET = "build-documents"


def object_key(tenant_id: str, asset_id: str, digest: str) -> str:
    return f"tenants/{tenant_id}/assets/{asset_id}/{digest}"


@pytest.mark.asyncio
async def test_real_sweeper_deletes_old_orphans_and_keeps_recent_referenced_and_unparseable(backend, tenant_a):
    client = object_store()
    storage = S3ObjectStorage.from_settings()
    unique = uuid.uuid4().hex.encode()
    digest = hashlib.sha256(unique).hexdigest()
    old_key = object_key(str(uuid.uuid4()), str(uuid.uuid4()), digest)
    client.put_object(Bucket=BUCKET, Key=old_key, Body=unique)

    try:
        old_sweep = await sweep_orphaned_objects(
            storage,
            bucket=BUCKET,
            grace_period_seconds=3600,
            now=datetime.now(timezone.utc) + timedelta(days=2),
        )
        with pytest.raises(ObjectNotFoundError):
            await storage.head(old_key)

        recent_id = str(uuid.uuid4())
        recent_key = object_key(str(uuid.uuid4()), recent_id, hashlib.sha256(b"recent").hexdigest())
        client.put_object(Bucket=BUCKET, Key=recent_key, Body=b"recent")
        unparseable_key = f"tenants/not-a-managed-key/{uuid.uuid4().hex}"
        client.put_object(Bucket=BUCKET, Key=unparseable_key, Body=b"keep")
        asset = create_asset(backend, tenant_a)
        row_key = asset["storage_uri"].split("/", 3)[3]

        current_sweep = await sweep_orphaned_objects(storage, bucket=BUCKET, grace_period_seconds=3600)
        second_sweep = await sweep_orphaned_objects(storage, bucket=BUCKET, grace_period_seconds=3600)

        assert old_sweep.deleted >= 1
        assert current_sweep.deleted == 0
        assert current_sweep.unparseable == 1
        assert second_sweep.deleted == 0
        for key in (recent_key, unparseable_key, row_key):
            await storage.head(key)
    finally:
        client.close()

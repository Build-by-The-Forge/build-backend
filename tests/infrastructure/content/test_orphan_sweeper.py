from datetime import datetime, timedelta, timezone

import pytest

from app.application.content.upload import object_key, storage_uri_for
from app.domain.content.asset import ContentAsset
from app.domain.content.storage import ObjectStoragePage, StoredObjectSummary
from app.infrastructure.content.orphan_sweeper import parse_managed_object_key, sweep_object_pages

BUCKET = "build-documents"
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
GRACE = 3600


class FakeStorage:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []
        self.deleted = []

    async def list_page(self, *, prefix, continuation_token=None, max_keys=1000):
        self.requests.append((prefix, continuation_token, max_keys))
        index = 0 if continuation_token is None else int(continuation_token)
        objects, next_token = self.pages[index]
        return ObjectStoragePage(objects=tuple(objects), continuation_token=next_token)

    async def delete(self, key):
        self.deleted.append(key)


def stored(key, modified):
    return StoredObjectSummary(key=key, last_modified=modified)


def asset(asset_id, tenant_id, sha):
    return ContentAsset.create(
        source_id="source",
        tenant_id=tenant_id,
        file_name="document.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        content_sha256=sha,
        storage_uri=storage_uri_for(BUCKET, object_key(tenant_id, asset_id, sha)),
        created_by="user",
        created_by_email="user@example.invalid",
        asset_id=asset_id,
    )


def test_managed_object_key_parser_refuses_noncanonical_keys():
    assert parse_managed_object_key(f"tenants/t1/assets/a1/{'a' * 64}") == ("t1", "a1")
    assert parse_managed_object_key(f"tenants/t1/assets/a1/{'A' * 64}") is None
    assert parse_managed_object_key("tenants/t1/assets/a1/not-a-digest") is None
    assert parse_managed_object_key("tenants/t1/assets/a1/" + "a" * 64 + "/extra") is None


@pytest.mark.asyncio
async def test_sweeper_queries_each_page_once_and_deletes_only_old_unreferenced_objects():
    row_asset = asset("a-row", "t1", "a" * 64)
    old_orphan_key = f"tenants/t1/assets/a-missing/{'b' * 64}"
    mismatch_key = f"tenants/t-other/assets/a-row/{'c' * 64}"
    recent_key = f"tenants/t1/assets/a-recent/{'d' * 64}"
    malformed_key = "tenants/not-a-managed-key"
    storage = FakeStorage(
        [
            (
                [
                    stored(row_asset.storage_uri.removeprefix(f"s3://{BUCKET}/"), NOW - timedelta(days=2)),
                    stored(old_orphan_key, NOW - timedelta(days=2)),
                ],
                "1",
            ),
            (
                [
                    stored(mismatch_key, NOW - timedelta(days=2)),
                    stored(recent_key, NOW - timedelta(minutes=30)),
                    stored(malformed_key, NOW - timedelta(days=2)),
                ],
                None,
            ),
        ]
    )
    lookup_calls = []
    rows = {row_asset.id: row_asset}

    async def lookup(asset_ids):
        lookup_calls.append(set(asset_ids))
        return [rows[asset_id] for asset_id in asset_ids if asset_id in rows]

    result = await sweep_object_pages(
        storage,
        lookup,
        bucket=BUCKET,
        grace_period_seconds=GRACE,
        now=NOW,
    )

    assert storage.deleted == [old_orphan_key, mismatch_key]
    assert lookup_calls == [{"a-row", "a-missing"}, {"a-row", "a-recent"}]
    assert storage.requests == [("tenants/", None, 1000), ("tenants/", "1", 1000)]
    assert (result.pages, result.scanned, result.deleted, result.kept, result.unparseable) == (2, 5, 2, 3, 1)


@pytest.mark.asyncio
async def test_sweeper_second_pass_does_not_delete_anything_again():
    old_key = f"tenants/t1/assets/a-missing/{'e' * 64}"
    storage = FakeStorage([([stored(old_key, NOW - timedelta(days=2))], None)])

    async def no_assets(_asset_ids):
        return []

    first = await sweep_object_pages(storage, no_assets, bucket=BUCKET, grace_period_seconds=GRACE, now=NOW)
    storage.pages = [([], None)]
    second = await sweep_object_pages(storage, no_assets, bucket=BUCKET, grace_period_seconds=GRACE, now=NOW)

    assert first.deleted == 1
    assert second.deleted == 0
    assert storage.deleted == [old_key]


@pytest.mark.asyncio
async def test_sweeper_rejects_short_grace_and_naive_clock():
    storage = FakeStorage([([], None)])

    async def no_assets(_asset_ids):
        return []

    with pytest.raises(ValueError, match="one hour"):
        await sweep_object_pages(storage, no_assets, bucket=BUCKET, grace_period_seconds=GRACE - 1, now=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        await sweep_object_pages(
            storage,
            no_assets,
            bucket=BUCKET,
            grace_period_seconds=GRACE,
            now=NOW.replace(tzinfo=None),
        )

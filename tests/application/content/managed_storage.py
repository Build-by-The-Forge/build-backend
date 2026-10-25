"""Test helpers: assets in managed storage, as the upload service writes
them (P3-1 PR 3b). Only such assets may be queued or dispatched."""

from __future__ import annotations

from app.application.content.upload import object_key, storage_uri_for
from app.domain.content.asset import ContentAsset
from app.domain.content.storage import ObjectInfo, ObjectNotFoundError

BUCKET = "build-documents"


class StoredObjects:
    """The part of ObjectStorage the dispatch check uses (head), in memory."""

    def __init__(self) -> None:
        self.objects: dict[str, ObjectInfo] = {}
        self.head_error: Exception | None = None

    async def head(self, key: str) -> ObjectInfo:
        if self.head_error is not None:
            raise self.head_error
        if key not in self.objects:
            raise ObjectNotFoundError("missing")
        return self.objects[key]


OBJECTS = StoredObjects()


def managed(asset: ContentAsset, objects: StoredObjects = OBJECTS) -> ContentAsset:
    """Point ``asset`` at its managed key and store a matching object. A
    platform asset (no tenant) cannot be managed and is left as it is."""
    if asset.tenant_id is None:
        return asset
    key = object_key(asset.tenant_id, asset.id, asset.content_sha256)
    asset.storage_uri = storage_uri_for(BUCKET, key)
    objects.objects[key] = ObjectInfo(
        key=key, size_bytes=asset.file_size_bytes, content_type=asset.mime_type, sha256=asset.content_sha256
    )
    return asset

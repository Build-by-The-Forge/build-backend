"""Creating assets the only supported way, through the upload endpoint
(P3-1 PR 3b), for tests whose subject is something else."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from app.domain.content.storage import ObjectInfo, ObjectNotFoundError, StoredObject

BUCKET = "build-documents"


class InMemoryStorage:
    """ObjectStorage in memory: what upload stores, dispatch can head."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key, data, *, content_type, expected_sha256=None):
        raw = data.read() if hasattr(data, "read") else bytes(data)
        self.objects[key] = raw
        return StoredObject(key=key, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), content_type=content_type)

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
        self.objects.pop(key, None)


def pdf_bytes() -> bytes:
    """A small PDF, unique per call (duplicate content is tenant-wide)."""
    return b"%PDF-1.7\n" + uuid4().hex.encode() * 20


def upload_asset(
    client, source_id: str, *, headers: dict, name: str = "notes.pdf", data: bytes | None = None, key: str | None = None
):
    request_headers = dict(headers) | {"Idempotency-Key": key or f"k-{uuid4().hex}", "Content-Type": "application/octet-stream"}
    return client.post(
        f"/content/sources/{source_id}/assets/upload",
        params={"file_name": name},
        headers=request_headers,
        content=data if data is not None else pdf_bytes(),
    )

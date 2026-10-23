"""Receive an upload's raw body (P3-1 PR 2, docs/p3-1-pr2-upload-design.md
sections 2 and 3): stream it into a spooled temporary file, hashing and
counting as it arrives.

- The size limit is enforced while reading. A missing or dishonest
  Content-Length changes nothing (the body-limit middleware enforces the
  same limit in front of the app).
- The read deadline covers the whole body, not just the connection.
- The temporary file is closed, and so removed, on every path: success,
  error, timeout and cancellation.
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.requests import Request

from app.application.content.upload import (
    SIGNATURE_BYTES,
    UploadedBody,
    UploadReadTimeoutError,
    UploadTooLargeError,
)

# Bodies up to 1 MiB stay in memory; larger ones spill to a temporary file.
_IN_MEMORY_BYTES = 1024 * 1024


@asynccontextmanager
async def received_upload(request: Request, *, max_bytes: int, timeout_seconds: float) -> AsyncIterator[UploadedBody]:
    spool = tempfile.SpooledTemporaryFile(max_size=_IN_MEMORY_BYTES)
    try:
        digest = hashlib.sha256()
        size = 0
        head = b""
        try:
            async with asyncio.timeout(timeout_seconds):
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLargeError(f"the upload exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    spool.write(chunk)
                    if len(head) < SIGNATURE_BYTES:
                        head += chunk[: SIGNATURE_BYTES - len(head)]
        except TimeoutError:
            raise UploadReadTimeoutError(f"the upload was not received within {timeout_seconds:g} s") from None
        spool.seek(0)
        yield UploadedBody(file=spool, size_bytes=size, sha256=digest.hexdigest(), head=head)
    finally:
        spool.close()

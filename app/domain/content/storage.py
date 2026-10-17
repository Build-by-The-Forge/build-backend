"""Object storage for uploaded documents (Phase 3, D1), as the application
sees it: put, get, head and delete by key, with SHA-256 integrity.

Checksum semantics:
- ``put`` computes SHA-256 from the exact bytes it stores and returns it.
  When the caller passes ``expected_sha256``, a mismatch is refused before
  anything is written.
- ``get`` verifies the bytes it reads against the caller's
  ``expected_sha256``, which comes from the backend's own record. The
  ``sha256`` the store reports from its metadata is informational only.
- An S3 ETag is never treated as a checksum: for multipart uploads, and on
  some providers, it is not even an MD5 of the content.

Every failure is one of the typed errors below. Unknown provider errors
stay ``ObjectStorageError``; they are never reported as "not found".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str
    content_type: str


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size_bytes: int
    content_type: str | None
    # From the store's object metadata: informational, not proof.
    sha256: str | None


class ObjectStorageError(Exception):
    """Base error. ``error_code`` is stable for callers and logs;
    ``is_retryable`` says whether the same request may succeed later."""

    default_code = "OBJECT_STORAGE_ERROR"
    default_retryable = False

    def __init__(self, message: str, *, error_code: str | None = None, is_retryable: bool | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code or self.default_code
        self.is_retryable = self.default_retryable if is_retryable is None else is_retryable


class ObjectNotFoundError(ObjectStorageError):
    default_code = "OBJECT_NOT_FOUND"


class ObjectStorageAccessDeniedError(ObjectStorageError):
    """The credentials are refused or lack permission for the operation.
    Not retryable: retrying with the same credentials cannot succeed."""

    default_code = "OBJECT_STORAGE_ACCESS_DENIED"


class ObjectStorageConfigurationError(ObjectStorageError):
    """Storage is not configured, or points at something that does not
    exist (e.g. no such bucket)."""

    default_code = "OBJECT_STORAGE_NOT_CONFIGURED"


class ObjectStorageUnavailableError(ObjectStorageError):
    """A transient failure: the service is unreachable, slow or failing."""

    default_code = "OBJECT_STORAGE_UNAVAILABLE"
    default_retryable = True


class ObjectIntegrityError(ObjectStorageError):
    """Bytes did not match the expected SHA-256. Permanent for stored
    objects; a corruption in transit is raised retryable."""

    default_code = "OBJECT_INTEGRITY_MISMATCH"


class ObjectTooLargeError(ObjectStorageError):
    default_code = "OBJECT_TOO_LARGE"


class InvalidObjectKeyError(ObjectStorageError):
    default_code = "INVALID_OBJECT_KEY"


class ObjectStorage(Protocol):
    async def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str,
        expected_sha256: str | None = None,
    ) -> StoredObject:
        raise NotImplementedError

    async def get(self, key: str, *, expected_sha256: str, max_bytes: int) -> bytes:
        raise NotImplementedError

    async def head(self, key: str) -> ObjectInfo:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

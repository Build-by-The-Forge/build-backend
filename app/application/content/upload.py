"""Document upload: from verified request and streamed bytes to a stored
object and a committed asset row (P3-1 PR 2, docs/p3-1-pr2-upload-design.md).

The API layer streams and hashes the body (UploadedBody); this module
validates it, applies the idempotency contract (design section 5), stores
the object and commits the row, compensating when the commit fails (section
6).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

import structlog
from sqlalchemy.exc import IntegrityError

from app.application.common.uow import ContentUnitOfWorkFactory
from app.core.metrics import content_upload_orphaned_objects_total
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import SourceStatus, VisibilityScope
from app.domain.content.storage import (
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    ObjectStorageUnavailableError,
)
from app.events.event_bus import EventBus

logger = structlog.get_logger(__name__)

# Fixed namespace for upload asset ids: uuid5(namespace, scope:source:key).
BUILD_UPLOAD_NAMESPACE = uuid.UUID("5f0c8a52-7d1e-4b8e-9a43-2c6f1e0b7d93")

_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_MAX_FILE_NAME = 255

# Allow-list: signature, MIME type, accepted extensions. A signature is a
# preliminary check, not proof that the file is valid (P3-2 validates).
_TYPES: tuple[tuple[bytes, str, tuple[str, ...]], ...] = (
    (b"%PDF-", "application/pdf", (".pdf",)),
    (b"\x89PNG\r\n\x1a\n", "image/png", (".png",)),
    (b"\xff\xd8\xff", "image/jpeg", (".jpg", ".jpeg")),
)
SIGNATURE_BYTES = max(len(signature) for signature, _, _ in _TYPES)


class UploadError(Exception):
    """A refused or failed upload. ``status_code`` and ``code`` go to the
    client; the message never contains bytes, keys or credentials."""

    status_code = 500
    code = "UPLOAD_FAILED"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class InvalidUploadRequestError(UploadError):
    status_code = 400
    code = "INVALID_UPLOAD"


class UnsupportedUploadTypeError(UploadError):
    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"


class UploadSourceNotFoundError(UploadError):
    status_code = 404
    code = "SOURCE_NOT_FOUND"


class PlatformSourceUploadNotSupportedError(UploadError):
    status_code = 403
    code = "PLATFORM_SOURCE_UPLOAD_NOT_SUPPORTED"


class UploadSourceRevokedError(UploadError):
    status_code = 409
    code = "SOURCE_REVOKED"


class IdempotencyKeyReusedError(UploadError):
    status_code = 409
    code = "IDEMPOTENCY_KEY_REUSED"


class UploadStorageUnavailableError(UploadError):
    status_code = 503
    code = "OBJECT_STORAGE_UNAVAILABLE"


class UploadTooLargeError(UploadError):
    status_code = 413
    code = "UPLOAD_TOO_LARGE"


class UploadReadTimeoutError(UploadError):
    status_code = 408
    code = "UPLOAD_READ_TIMEOUT"


class DuplicateContentError(UploadError):
    """The tenant already has an asset with these exact bytes: the database
    keeps one asset per (tenant, SHA-256), uq_content_assets_tenant_hash.
    ``existing_asset_id`` is for the API to reveal only to a caller who may
    read assets."""

    status_code = 409
    code = "DUPLICATE_CONTENT"

    def __init__(self, existing_asset_id: str) -> None:
        super().__init__("this tenant already has an asset with exactly this content")
        self.existing_asset_id = existing_asset_id


@dataclass(frozen=True, slots=True)
class UploadedBody:
    """The request body as received: a seekable file positioned at 0, with
    the size and SHA-256 of exactly its bytes and its first bytes."""

    file: BinaryIO
    size_bytes: int
    sha256: str
    head: bytes


@dataclass(frozen=True, slots=True)
class UploadResult:
    asset: ContentAsset
    created: bool


def validate_idempotency_key(key: str | None) -> str:
    if key is None or not _IDEMPOTENCY_KEY.fullmatch(key):
        raise InvalidUploadRequestError(
            "Idempotency-Key is required: 1-128 characters from A-Z a-z 0-9 . _ : -",
            code="INVALID_IDEMPOTENCY_KEY",
        )
    return key


def validate_file_name(name: str | None) -> str:
    if (
        not name
        or len(name) > _MAX_FILE_NAME
        or "/" in name
        or "\\" in name
        or name in (".", "..")
        or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name)
    ):
        raise InvalidUploadRequestError(
            "file_name must be 1-255 characters, without path separators or control characters",
            code="INVALID_FILE_NAME",
        )
    return name


def detect_mime_type(head: bytes, file_name: str) -> str:
    """The MIME type from the file's signature. The extension must agree."""
    extension = PurePosixPath(file_name.lower()).suffix
    for signature, mime_type, extensions in _TYPES:
        if head.startswith(signature):
            if extension not in extensions:
                raise UnsupportedUploadTypeError(
                    f"the content is {mime_type}, but the file name ends in {extension or 'no extension'}"
                )
            return mime_type
    raise UnsupportedUploadTypeError("only PDF, PNG and JPEG documents are accepted")


def derive_asset_id(tenant_id: str, source_id: str, idempotency_key: str) -> str:
    return str(uuid.uuid5(BUILD_UPLOAD_NAMESPACE, f"{tenant_id}:{source_id}:{idempotency_key}"))


def object_key(tenant_id: str, asset_id: str, sha256: str) -> str:
    return f"tenants/{tenant_id}/assets/{asset_id}/{sha256}"


def storage_uri_for(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def managed_storage_key(asset: ContentAsset, bucket: str) -> str | None:
    """The object key of ``asset`` if its ``storage_uri`` is exactly the one
    the upload service writes for this row: the configured bucket and the
    row's own tenant, id and SHA-256. Otherwise None (design section 10).

    Only such a reference may reach the AI-service. A legacy or
    client-supplied URI is never trusted for being well formed: a foreign
    bucket, another tenant's or asset's prefix, another hash, a platform
    row, extra segments or any other spelling all return None.
    """
    if not asset.tenant_id or not bucket:
        return None
    key = object_key(asset.tenant_id, asset.id, asset.content_sha256)
    if asset.storage_uri != storage_uri_for(bucket, key):
        return None
    return key


class ContentAssetUploadService:
    def __init__(
        self,
        *,
        uow_factory: ContentUnitOfWorkFactory,
        storage_factory: Callable[[], ObjectStorage],
        bucket: Callable[[], str],
        event_bus: EventBus | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage_factory = storage_factory
        self._bucket = bucket
        self._event_bus = event_bus or EventBus()

    async def upload(
        self,
        *,
        source_id: str,
        tenant_id: str,
        user_id: str,
        user_email: str,
        file_name: str | None,
        idempotency_key: str | None,
        body: UploadedBody,
        correlation_id: str | None = None,
    ) -> UploadResult:
        key = validate_idempotency_key(idempotency_key)
        name = validate_file_name(file_name)
        if body.size_bytes == 0:
            raise InvalidUploadRequestError("the upload is empty", code="EMPTY_UPLOAD")
        mime_type = detect_mime_type(body.head, name)

        asset_id = derive_asset_id(tenant_id, source_id, key)
        storage_key = object_key(tenant_id, asset_id, body.sha256)

        existing = await self._existing(source_id, tenant_id, asset_id)
        # The storage client is created only once it is needed: a request
        # refused above never depends on storage configuration.
        storage = self._storage()
        if existing is not None:
            return await self._replay(existing, body, storage, storage_key)
        same_content = await self._asset_by_hash(body.sha256, tenant_id)
        if same_content is not None:
            raise DuplicateContentError(same_content.id)

        await self._store(storage, storage_key, body, mime_type)

        asset = ContentAsset.create(
            source_id=source_id,
            tenant_id=tenant_id,
            file_name=name,
            mime_type=mime_type,
            file_size_bytes=body.size_bytes,
            content_sha256=body.sha256,
            storage_uri=storage_uri_for(self._bucket(), storage_key),
            created_by=user_id,
            created_by_email=user_email,
            metadata={"upload": {"detected_mime_type": mime_type}},
            asset_id=asset_id,
        )
        events = asset.pull_events()
        try:
            async with self._uow_factory() as uow:
                saved = await uow.assets.insert_asset(asset)  # insert only, never an update
        except IntegrityError:
            # A concurrent transaction committed first. Which constraint lost
            # is decided by what was committed, not by the error's text:
            # - a row with our id is a primary-key race on the same key;
            # - a row with our content is the (tenant, SHA-256) rule.
            try:
                winner = await self._asset_by_id(asset_id)
            except Exception:
                # The winner is unknown, so the object may be its: keep it, reported.
                self._report_kept_object(asset_id, correlation_id, "race_unresolved")
                raise
            if winner is not None:
                if winner.content_sha256 == body.sha256:
                    return UploadResult(winner, created=False)  # its object is ours: same key
                await self._compensate(storage, storage_key, asset_id, correlation_id, "concurrent_key_reuse")
                raise IdempotencyKeyReusedError("this Idempotency-Key was already used for different content") from None
            await self._compensate(storage, storage_key, asset_id, correlation_id, "concurrent_duplicate_content")
            same_content = await self._asset_by_hash(body.sha256, tenant_id)
            if same_content is not None:
                raise DuplicateContentError(same_content.id) from None
            raise
        except Exception:
            referenced = await self._referenced(asset_id, body.sha256)
            if referenced is None:
                self._report_kept_object(asset_id, correlation_id, "commit_unverified")
            elif not referenced:
                await self._compensate(storage, storage_key, asset_id, correlation_id, "commit_failed")
            raise

        if events:
            self._event_bus.publish_all(events)
        return UploadResult(saved, created=True)

    def _storage(self) -> ObjectStorage:
        try:
            return self._storage_factory()
        except ObjectStorageError as exc:
            # An operator problem, not the client's: 500, with no Retry-After.
            raise UploadError("object storage is not configured", code="OBJECT_STORAGE_NOT_CONFIGURED") from exc

    async def _existing(self, source_id: str, tenant_id: str, asset_id: str) -> ContentAsset | None:
        async with self._uow_factory() as uow:
            source = await uow.sources.get_source_by_id(source_id)
            if source is None:
                raise UploadSourceNotFoundError("no such source")
            if source.visibility == VisibilityScope.PLATFORM:
                raise PlatformSourceUploadNotSupportedError("uploads to platform-scoped sources are not supported")
            if source.tenant_id != tenant_id:
                # Indistinguishable from a missing source (design section 1).
                raise UploadSourceNotFoundError("no such source")
            if source.status == SourceStatus.REVOKED:
                raise UploadSourceRevokedError("the source is revoked")
            existing = await uow.assets.get_asset_by_id(asset_id)
        if existing is not None and (existing.source_id != source_id or existing.tenant_id != tenant_id):
            raise UploadError("an asset id collided across scopes", code="ASSET_ID_COLLISION")
        return existing

    async def _replay(self, existing: ContentAsset, body: UploadedBody, storage: ObjectStorage, storage_key: str) -> UploadResult:
        if existing.content_sha256 != body.sha256:
            raise IdempotencyKeyReusedError("this Idempotency-Key was already used for different content")
        try:
            await storage.head(storage_key)
        except ObjectNotFoundError:
            # The row exists but its object does not: heal it from the
            # identical bytes (same key, same SHA-256).
            await self._store(storage, storage_key, body, existing.mime_type)
        except ObjectStorageUnavailableError as exc:
            raise UploadStorageUnavailableError("object storage is unavailable; retry later") from exc
        except ObjectStorageError as exc:
            raise UploadError("object storage failed", code="OBJECT_STORAGE_FAILURE") from exc
        return UploadResult(existing, created=False)

    async def _store(self, storage: ObjectStorage, storage_key: str, body: UploadedBody, mime_type: str) -> None:
        body.file.seek(0)
        try:
            await storage.put(storage_key, body.file, content_type=mime_type, expected_sha256=body.sha256)
        except (ObjectStorageUnavailableError, ObjectIntegrityError) as exc:
            if getattr(exc, "is_retryable", False):
                raise UploadStorageUnavailableError("object storage is unavailable; retry later") from exc
            raise UploadError("the upload changed while it was stored", code="UPLOAD_INTEGRITY") from exc
        except ObjectStorageError as exc:
            raise UploadError("object storage failed", code="OBJECT_STORAGE_FAILURE") from exc

    async def _asset_by_id(self, asset_id: str) -> ContentAsset | None:
        async with self._uow_factory() as uow:
            return await uow.assets.get_asset_by_id(asset_id)

    async def _asset_by_hash(self, sha256: str, tenant_id: str) -> ContentAsset | None:
        """Any asset of the tenant with this content, whatever its status:
        uq_content_assets_tenant_hash applies to revoked rows too."""
        async with self._uow_factory() as uow:
            return await uow.assets.get_asset_by_hash(sha256, tenant_id)

    async def _referenced(self, asset_id: str, sha256: str) -> bool | None:
        """Whether a committed row references the object we stored (same id
        and SHA-256, hence the same key); None when that cannot be read.
        Unknown is never deleted: it might be in use."""
        try:
            row = await self._asset_by_id(asset_id)
        except Exception:
            return None
        return row is not None and row.content_sha256 == sha256

    async def _compensate(
        self, storage: ObjectStorage, storage_key: str, asset_id: str, correlation_id: str | None, reason: str
    ) -> None:
        try:
            await storage.delete(storage_key)
        except Exception as exc:
            error_code = getattr(exc, "error_code", type(exc).__name__)
            content_upload_orphaned_objects_total.labels(reason=reason).inc()
            logger.warning(
                "upload_compensation_failed",
                asset_id=asset_id,
                correlation_id=correlation_id,
                reason=reason,
                error_code=error_code,
            )

    @staticmethod
    def _report_kept_object(asset_id: str, correlation_id: str | None, reason: str) -> None:
        """An object kept because whether a row references it could not be
        read: possibly an orphan, so it reaches the same log and metric."""
        content_upload_orphaned_objects_total.labels(reason=reason).inc()
        logger.warning("upload_compensation_skipped", asset_id=asset_id, correlation_id=correlation_id, reason=reason)

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.domain.content.enums import AssetStatus, IngestionStatus
from app.events.base import DomainEvent

_HEX_64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass
class ContentAsset:
    id: str
    source_id: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    content_sha256: str
    storage_uri: str
    status: AssetStatus
    ingestion_status: IngestionStatus
    created_by: str
    created_by_email: str
    tenant_id: str | None = None
    asset_version: int = 1
    parent_asset_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        source_id: str,
        file_name: str,
        mime_type: str,
        file_size_bytes: int,
        content_sha256: str,
        storage_uri: str,
        created_by: str,
        created_by_email: str,
        tenant_id: str | None = None,
        asset_version: int = 1,
        parent_asset_id: str | None = None,
        status: AssetStatus | str = AssetStatus.ACTIVE,
        ingestion_status: IngestionStatus | str = IngestionStatus.UPLOADED,
        metadata: dict[str, Any] | None = None,
        asset_id: str | None = None,
    ) -> ContentAsset:
        if not source_id.strip():
            raise ValueError("source_id cannot be empty")
        if not file_name.strip():
            raise ValueError("file_name cannot be empty")
        if not mime_type.strip():
            raise ValueError("mime_type cannot be empty")
        if file_size_bytes <= 0:
            raise ValueError("file_size_bytes must be greater than 0")
        clean_sha = content_sha256.strip().lower()
        if not _HEX_64_PATTERN.match(clean_sha):
            raise ValueError("content_sha256 must be a valid 64-character hex string")
        if not storage_uri.strip():
            raise ValueError("storage_uri cannot be empty")
        if not created_by.strip():
            raise ValueError("created_by cannot be empty")
        if not created_by_email.strip():
            raise ValueError("created_by_email cannot be empty")
        if asset_version < 1:
            raise ValueError("asset_version must be at least 1")

        st = AssetStatus(status) if isinstance(status, str) else status
        ing_st = IngestionStatus(ingestion_status) if isinstance(ingestion_status, str) else ingestion_status

        now = datetime.now(timezone.utc)
        asset = cls(
            id=asset_id or str(uuid4()),
            source_id=source_id.strip(),
            tenant_id=tenant_id.strip() if tenant_id else None,
            file_name=file_name.strip(),
            mime_type=mime_type.strip().lower(),
            file_size_bytes=file_size_bytes,
            content_sha256=clean_sha,
            storage_uri=storage_uri.strip(),
            asset_version=asset_version,
            parent_asset_id=parent_asset_id.strip() if parent_asset_id else None,
            status=st,
            ingestion_status=ing_st,
            metadata=dict(metadata) if metadata is not None else {},
            created_by=created_by.strip(),
            created_by_email=created_by_email.strip(),
            created_at=now,
            updated_at=now,
        )

        asset._events.append(
            DomainEvent(
                event_type="content.asset_registered",
                payload={
                    "asset_id": asset.id,
                    "source_id": asset.source_id,
                    "tenant_id": asset.tenant_id,
                    "file_name": asset.file_name,
                    "content_sha256": asset.content_sha256,
                    "asset_version": asset.asset_version,
                    "storage_uri": asset.storage_uri,
                },
            )
        )
        return asset

    def create_version(
        self,
        file_name: str,
        mime_type: str,
        file_size_bytes: int,
        content_sha256: str,
        storage_uri: str,
        created_by: str,
        created_by_email: str,
        metadata: dict[str, Any] | None = None,
        asset_id: str | None = None,
    ) -> ContentAsset:
        """Creates an updated edition/version of this asset, transitioning current asset to SUPERSEDED."""
        if self.status == AssetStatus.REVOKED:
            raise ValueError("cannot create a new version of a revoked asset")

        clean_new_sha = content_sha256.strip().lower()
        if clean_new_sha == self.content_sha256:
            raise ValueError("new version must have different content bytes (SHA-256 is identical to current version)")

        new_asset = ContentAsset.create(
            source_id=self.source_id,
            tenant_id=self.tenant_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            content_sha256=clean_new_sha,
            storage_uri=storage_uri,
            asset_version=self.asset_version + 1,
            parent_asset_id=self.id,
            status=AssetStatus.ACTIVE,
            ingestion_status=IngestionStatus.UPLOADED,
            metadata=metadata,
            created_by=created_by,
            created_by_email=created_by_email,
            asset_id=asset_id,
        )

        self.status = AssetStatus.SUPERSEDED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.asset_superseded",
                payload={
                    "asset_id": self.id,
                    "superseded_by_asset_id": new_asset.id,
                    "source_id": self.source_id,
                    "version": self.asset_version,
                },
            )
        )
        return new_asset

    def revoke(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("revocation reason cannot be empty")
        if self.status == AssetStatus.REVOKED:
            return

        self.status = AssetStatus.REVOKED
        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.asset_revoked",
                payload={
                    "asset_id": self.id,
                    "source_id": self.source_id,
                    "reason": reason.strip(),
                },
            )
        )

    def update_ingestion_status(
        self,
        ingestion_status: IngestionStatus | str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        new_status = IngestionStatus(ingestion_status) if isinstance(ingestion_status, str) else ingestion_status
        if self.ingestion_status == new_status:
            return

        self.ingestion_status = new_status
        if error_code is not None:
            self.metadata["error_code"] = error_code
        if error_message is not None:
            self.metadata["error_message"] = error_message

        self.touch()
        self._events.append(
            DomainEvent(
                event_type="content.asset_ingestion_status_updated",
                payload={
                    "asset_id": self.id,
                    "source_id": self.source_id,
                    "ingestion_status": self.ingestion_status.value,
                    "error_code": error_code,
                },
            )
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.content.enums import AssetStatus, IngestionStatus


@dataclass(frozen=True, slots=True)
class RegisterContentAssetCommand:
    source_id: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    content_sha256: str
    storage_uri: str
    created_by: str
    created_by_email: str
    tenant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    asset_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreateAssetVersionCommand:
    parent_asset_id: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    content_sha256: str
    storage_uri: str
    created_by: str
    created_by_email: str
    metadata: dict[str, Any] = field(default_factory=dict)
    asset_id: str | None = None


@dataclass(frozen=True, slots=True)
class RevokeContentAssetCommand:
    asset_id: str
    reason: str
    revoked_by: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetContentAssetQuery:
    asset_id: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class FindAssetByHashQuery:
    content_sha256: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class ListContentAssetsQuery:
    source_id: str | None = None
    tenant_id: str | None = None
    status: AssetStatus | None = None
    ingestion_status: IngestionStatus | None = None
    include_platform: bool = True
    limit: int = 50
    offset: int = 0

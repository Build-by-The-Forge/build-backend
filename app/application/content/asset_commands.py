from __future__ import annotations

from dataclasses import dataclass

from app.domain.content.enums import AssetStatus, IngestionStatus


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

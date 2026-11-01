from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.content.ai_report import public_failure_message, safe_error_code
from app.domain.content.asset import ContentAsset


class ContentAssetRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """A failure's text comes from its code, including on rows stored before that rule."""
    if "error_message" not in metadata:
        return metadata
    return {
        **metadata,
        "error_code": safe_error_code(metadata.get("error_code")),
        "error_message": public_failure_message(metadata.get("error_code")),
    }


class ContentAssetResponse(BaseModel):
    id: str
    source_id: str
    tenant_id: str | None = None
    file_name: str
    mime_type: str
    file_size_bytes: int
    content_sha256: str
    storage_uri: str
    asset_version: int
    parent_asset_id: str | None = None
    status: str
    ingestion_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_by_email: str
    created_at: datetime
    updated_at: datetime
    is_deduplicated: bool = False

    @classmethod
    def from_domain(cls, asset: ContentAsset, is_deduplicated: bool = False) -> ContentAssetResponse:
        return cls(
            id=asset.id,
            source_id=asset.source_id,
            tenant_id=asset.tenant_id,
            file_name=asset.file_name,
            mime_type=asset.mime_type,
            file_size_bytes=asset.file_size_bytes,
            content_sha256=asset.content_sha256,
            storage_uri=asset.storage_uri,
            asset_version=asset.asset_version,
            parent_asset_id=asset.parent_asset_id,
            status=asset.status.value,
            ingestion_status=asset.ingestion_status.value,
            metadata=_public_metadata(asset.metadata),
            created_by=asset.created_by,
            created_by_email=asset.created_by_email,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            is_deduplicated=is_deduplicated,
        )

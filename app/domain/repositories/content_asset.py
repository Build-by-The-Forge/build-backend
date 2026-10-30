from __future__ import annotations

from typing import Protocol

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus


class ContentAssetRepository(Protocol):
    async def save_asset(self, asset: ContentAsset) -> ContentAsset:
        raise NotImplementedError

    async def insert_asset(self, asset: ContentAsset) -> ContentAsset:
        """Insert only: a row with the same id, or anything else violating a
        constraint, fails at flush or commit instead of being updated.
        Uploads depend on that for their idempotency contract."""
        raise NotImplementedError

    async def supersede_if_active(self, asset_id: str) -> bool:
        """Mark the asset superseded only if it is still active, in one
        conditional UPDATE; True if it was. The version transition depends on
        it: under the database's row lock, two concurrent versions of one
        asset cannot both succeed (P3-1 PR 3b, design section 9)."""
        raise NotImplementedError

    async def get_asset_by_id(self, asset_id: str) -> ContentAsset | None:
        raise NotImplementedError

    async def get_assets_by_ids(self, asset_ids: set[str]) -> list[ContentAsset]:
        raise NotImplementedError

    async def get_asset_by_hash(self, content_sha256: str, tenant_id: str | None = None) -> ContentAsset | None:
        raise NotImplementedError

    async def list_assets_by_source(self, source_id: str, limit: int = 50, offset: int = 0) -> tuple[list[ContentAsset], int]:
        raise NotImplementedError

    async def list_assets(
        self,
        tenant_id: str | None = None,
        source_id: str | None = None,
        status: AssetStatus | None = None,
        ingestion_status: IngestionStatus | None = None,
        include_platform: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentAsset], int]:
        raise NotImplementedError

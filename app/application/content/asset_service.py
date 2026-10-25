from __future__ import annotations

from app.application.common.uow import ContentUnitOfWorkFactory, ContentUnitOfWorkPort
from app.application.content.asset_commands import (
    FindAssetByHashQuery,
    GetContentAssetQuery,
    ListContentAssetsQuery,
    RevokeContentAssetCommand,
)
from app.application.content.asset_handlers import (
    FindAssetByHashHandler,
    GetContentAssetHandler,
    ListContentAssetsHandler,
    RevokeContentAssetHandler,
)
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus
from app.events.event_bus import EventBus


class ContentAssetService:
    def __init__(
        self,
        uow: ContentUnitOfWorkPort | None = None,
        event_bus: EventBus | None = None,
        uow_factory: ContentUnitOfWorkFactory | None = None,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus or EventBus()
        self._uow_factory = uow_factory

    async def revoke_asset(
        self,
        asset_id: str,
        reason: str,
        revoked_by: str,
        tenant_id: str | None = None,
    ) -> ContentAsset:
        cmd = RevokeContentAssetCommand(
            asset_id=asset_id,
            reason=reason,
            revoked_by=revoked_by,
            tenant_id=tenant_id,
        )

        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                handler = RevokeContentAssetHandler(uow, self._event_bus)
                return await handler.handle(cmd)

        if self._uow is None:
            raise RuntimeError("ContentAssetService requires uow or uow_factory")
        handler = RevokeContentAssetHandler(self._uow, self._event_bus)
        return await handler.handle(cmd)

    async def get_asset(
        self,
        asset_id: str,
        tenant_id: str | None = None,
    ) -> ContentAsset | None:
        query = GetContentAssetQuery(asset_id=asset_id, tenant_id=tenant_id)

        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                handler = GetContentAssetHandler(uow)
                return await handler.handle(query)

        if self._uow is None:
            raise RuntimeError("ContentAssetService requires uow or uow_factory")
        handler = GetContentAssetHandler(self._uow)
        return await handler.handle(query)

    async def find_by_hash(
        self,
        content_sha256: str,
        tenant_id: str | None = None,
    ) -> ContentAsset | None:
        query = FindAssetByHashQuery(content_sha256=content_sha256, tenant_id=tenant_id)

        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                handler = FindAssetByHashHandler(uow)
                return await handler.handle(query)

        if self._uow is None:
            raise RuntimeError("ContentAssetService requires uow or uow_factory")
        handler = FindAssetByHashHandler(self._uow)
        return await handler.handle(query)

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
        query = ListContentAssetsQuery(
            tenant_id=tenant_id,
            source_id=source_id,
            status=status,
            ingestion_status=ingestion_status,
            include_platform=include_platform,
            limit=limit,
            offset=offset,
        )

        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                handler = ListContentAssetsHandler(uow)
                return await handler.handle(query)

        if self._uow is None:
            raise RuntimeError("ContentAssetService requires uow or uow_factory")
        handler = ListContentAssetsHandler(self._uow)
        return await handler.handle(query)

from __future__ import annotations

from app.application.common.uow import ContentUnitOfWorkPort
from app.application.content.access import ContentNotFoundError, ensure_tenant_may_write
from app.application.content.asset_commands import (
    FindAssetByHashQuery,
    GetContentAssetQuery,
    ListContentAssetsQuery,
    RevokeContentAssetCommand,
)
from app.domain.content.asset import ContentAsset
from app.events.event_bus import EventBus


class RevokeContentAssetHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(self, cmd: RevokeContentAssetCommand) -> ContentAsset:
        asset = await self._uow.assets.get_asset_by_id(cmd.asset_id)
        if asset is None:
            raise ContentNotFoundError("asset not found")
        # Another tenant's asset is not found (it was a 403 that confirmed it
        # exists); platform assets are not revocable from a tenant (PR 3a).
        ensure_tenant_may_write(asset.tenant_id, cmd.tenant_id, what="asset")

        asset.revoke(cmd.reason)
        events = asset.pull_events()
        saved = await self._uow.assets.save_asset(asset)

        if self._event_bus and events:
            self._event_bus.publish_all(events)

        return saved


class GetContentAssetHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(self, query: GetContentAssetQuery) -> ContentAsset | None:
        asset = await self._uow.assets.get_asset_by_id(query.asset_id)
        if asset is None:
            return None
        if query.tenant_id is not None and asset.tenant_id is not None and asset.tenant_id != query.tenant_id:
            return None
        return asset


class FindAssetByHashHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(self, query: FindAssetByHashQuery) -> ContentAsset | None:
        return await self._uow.assets.get_asset_by_hash(query.content_sha256, query.tenant_id)


class ListContentAssetsHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(self, query: ListContentAssetsQuery) -> tuple[list[ContentAsset], int]:
        return await self._uow.assets.list_assets(
            tenant_id=query.tenant_id,
            source_id=query.source_id,
            status=query.status,
            ingestion_status=query.ingestion_status,
            include_platform=query.include_platform,
            limit=query.limit,
            offset=query.offset,
        )

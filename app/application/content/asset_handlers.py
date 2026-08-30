from __future__ import annotations

from app.application.common.uow import ContentUnitOfWorkPort
from app.application.content.asset_commands import (
    CreateAssetVersionCommand,
    FindAssetByHashQuery,
    GetContentAssetQuery,
    ListContentAssetsQuery,
    RegisterContentAssetCommand,
    RevokeContentAssetCommand,
)
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, SourceStatus, VisibilityScope
from app.events.event_bus import EventBus


class RegisterContentAssetHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(
        self, cmd: RegisterContentAssetCommand
    ) -> tuple[ContentAsset, bool]:
        """Registers a new content asset or returns the existing deduplicated asset if SHA-256 matches."""
        # 1. Validate ContentSource existence and accessibility
        source = await self._uow.sources.get_source_by_id(cmd.source_id)
        if source is None:
            raise ValueError(f"ContentSource with id '{cmd.source_id}' does not exist")
        if source.status == SourceStatus.REVOKED:
            raise ValueError(f"Cannot register asset against revoked source '{cmd.source_id}'")

        # 2. Scope validation
        if source.visibility == VisibilityScope.PLATFORM:
            target_tenant_id = None
        else:
            if cmd.tenant_id is None:
                raise ValueError("tenant_id is required for tenant-scoped content sources")
            if source.tenant_id != cmd.tenant_id:
                raise ValueError(
                    f"tenant_id mismatch: source belongs to tenant '{source.tenant_id}', got '{cmd.tenant_id}'"
                )
            target_tenant_id = cmd.tenant_id

        # 3. Deduplication Check (Tenant-scoped / Platform-scoped)
        existing = await self._uow.assets.get_asset_by_hash(
            cmd.content_sha256, target_tenant_id
        )
        if existing is not None and existing.status == AssetStatus.ACTIVE:
            # Deterministic reuse: skip redundant ingestion pipeline
            return existing, True

        # 4. Create and persist new ContentAsset
        asset = ContentAsset.create(
            source_id=cmd.source_id,
            tenant_id=target_tenant_id,
            file_name=cmd.file_name,
            mime_type=cmd.mime_type,
            file_size_bytes=cmd.file_size_bytes,
            content_sha256=cmd.content_sha256,
            storage_uri=cmd.storage_uri,
            created_by=cmd.created_by,
            created_by_email=cmd.created_by_email,
            metadata=cmd.metadata,
            asset_id=cmd.asset_id,
        )

        events = asset.pull_events()
        saved = await self._uow.assets.save_asset(asset)

        if self._event_bus and events:
            self._event_bus.publish_all(events)

        return saved, False


class CreateAssetVersionHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(self, cmd: CreateAssetVersionCommand) -> ContentAsset:
        parent = await self._uow.assets.get_asset_by_id(cmd.parent_asset_id)
        if parent is None:
            raise ValueError(f"Parent asset with id '{cmd.parent_asset_id}' does not exist")
        if parent.status == AssetStatus.REVOKED:
            raise ValueError("Cannot create a new version of a revoked asset")

        new_asset = parent.create_version(
            file_name=cmd.file_name,
            mime_type=cmd.mime_type,
            file_size_bytes=cmd.file_size_bytes,
            content_sha256=cmd.content_sha256,
            storage_uri=cmd.storage_uri,
            created_by=cmd.created_by,
            created_by_email=cmd.created_by_email,
            metadata=cmd.metadata,
            asset_id=cmd.asset_id,
        )

        # Save both parent (now SUPERSEDED) and new_asset (ACTIVE)
        parent_events = parent.pull_events()
        new_events = new_asset.pull_events()

        await self._uow.assets.save_asset(parent)
        saved_new = await self._uow.assets.save_asset(new_asset)

        all_events = parent_events + new_events
        if self._event_bus and all_events:
            self._event_bus.publish_all(all_events)

        return saved_new


class RevokeContentAssetHandler:
    def __init__(self, uow: ContentUnitOfWorkPort, event_bus: EventBus | None = None) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(self, cmd: RevokeContentAssetCommand) -> ContentAsset:
        asset = await self._uow.assets.get_asset_by_id(cmd.asset_id)
        if asset is None:
            raise ValueError(f"ContentAsset with id '{cmd.asset_id}' does not exist")

        if cmd.tenant_id is not None and asset.tenant_id is not None and asset.tenant_id != cmd.tenant_id:
            raise ValueError("Permission denied: asset belongs to another tenant")

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
        return await self._uow.assets.get_asset_by_hash(
            query.content_sha256, query.tenant_id
        )


class ListContentAssetsHandler:
    def __init__(self, uow: ContentUnitOfWorkPort) -> None:
        self._uow = uow

    async def handle(
        self, query: ListContentAssetsQuery
    ) -> tuple[list[ContentAsset], int]:
        return await self._uow.assets.list_assets(
            tenant_id=query.tenant_id,
            source_id=query.source_id,
            status=query.status,
            ingestion_status=query.ingestion_status,
            include_platform=query.include_platform,
            limit=query.limit,
            offset=query.offset,
        )

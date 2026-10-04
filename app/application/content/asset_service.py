from __future__ import annotations

from typing import Any

from app.application.common.uow import ContentUnitOfWorkFactory, ContentUnitOfWorkPort
from app.application.content.asset_commands import (
    CreateAssetVersionCommand,
    FindAssetByHashQuery,
    GetContentAssetQuery,
    ListContentAssetsQuery,
    RegisterContentAssetCommand,
    RevokeContentAssetCommand,
)
from app.application.content.asset_handlers import (
    CreateAssetVersionHandler,
    FindAssetByHashHandler,
    GetContentAssetHandler,
    ListContentAssetsHandler,
    RegisterContentAssetHandler,
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

    async def register_asset(
        self,
        source_id: str,
        file_name: str,
        mime_type: str,
        file_size_bytes: int,
        content_sha256: str,
        storage_uri: str,
        created_by: str,
        created_by_email: str,
        tenant_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        asset_id: str | None = None,
    ) -> tuple[ContentAsset, bool]:
        cmd = RegisterContentAssetCommand(
            source_id=source_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            content_sha256=content_sha256,
            storage_uri=storage_uri,
            created_by=created_by,
            created_by_email=created_by_email,
            tenant_id=tenant_id,
            metadata=metadata or {},
            asset_id=asset_id,
        )

        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                handler = RegisterContentAssetHandler(uow, self._event_bus)
                return await handler.handle(cmd)

        if self._uow is None:
            raise RuntimeError("ContentAssetService requires uow or uow_factory")
        handler = RegisterContentAssetHandler(self._uow, self._event_bus)
        return await handler.handle(cmd)

    async def create_version(
        self,
        parent_asset_id: str,
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
        cmd = CreateAssetVersionCommand(
            parent_asset_id=parent_asset_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            content_sha256=content_sha256,
            storage_uri=storage_uri,
            created_by=created_by,
            created_by_email=created_by_email,
            metadata=metadata or {},
            asset_id=asset_id,
        )

        if self._uow_factory is not None:
            async with self._uow_factory() as uow:
                handler = CreateAssetVersionHandler(uow, self._event_bus)
                return await handler.handle(cmd)

        if self._uow is None:
            raise RuntimeError("ContentAssetService requires uow or uow_factory")
        handler = CreateAssetVersionHandler(self._uow, self._event_bus)
        return await handler.handle(cmd)

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

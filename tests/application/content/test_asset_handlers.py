import pytest

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
from app.domain.content.enums import (
    AssetStatus,
    AuthorityLevel,
    ContentSourceType,
    IngestionStatus,
    SourceStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource
from app.events.event_bus import EventBus


class InMemoryContentSourceRepo:
    def __init__(self) -> None:
        self.sources: dict[str, ContentSource] = {}

    async def save_source(self, source: ContentSource) -> ContentSource:
        self.sources[source.id] = source
        return source

    async def get_source_by_id(self, source_id: str) -> ContentSource | None:
        return self.sources.get(source_id)

    async def get_source_by_code(self, code: str, tenant_id: str | None = None) -> ContentSource | None:
        for s in self.sources.values():
            if s.code == code and s.tenant_id == tenant_id:
                return s
        return None

    async def list_sources(
        self,
        tenant_id: str | None = None,
        source_type: ContentSourceType | None = None,
        authority_level: AuthorityLevel | None = None,
        status: SourceStatus | None = None,
        include_platform: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentSource], int]:
        results = list(self.sources.values())
        return results[offset : offset + limit], len(results)


class InMemoryContentAssetRepo:
    def __init__(self) -> None:
        self.assets: dict[str, ContentAsset] = {}

    async def save_asset(self, asset: ContentAsset) -> ContentAsset:
        self.assets[asset.id] = asset
        return asset

    async def get_asset_by_id(self, asset_id: str) -> ContentAsset | None:
        return self.assets.get(asset_id)

    async def get_asset_by_hash(self, content_sha256: str, tenant_id: str | None = None) -> ContentAsset | None:
        clean = content_sha256.strip().lower()
        for a in self.assets.values():
            if a.content_sha256 == clean and a.tenant_id == tenant_id:
                return a
        return None

    async def list_assets_by_source(self, source_id: str, limit: int = 50, offset: int = 0) -> tuple[list[ContentAsset], int]:
        res = [a for a in self.assets.values() if a.source_id == source_id]
        return res[offset : offset + limit], len(res)

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
        res = list(self.assets.values())
        if tenant_id is not None:
            if include_platform:
                res = [a for a in res if a.tenant_id == tenant_id or a.tenant_id is None]
            else:
                res = [a for a in res if a.tenant_id == tenant_id]
        if source_id is not None:
            res = [a for a in res if a.source_id == source_id]
        if status is not None:
            res = [a for a in res if a.status == status]
        if ingestion_status is not None:
            res = [a for a in res if a.ingestion_status == ingestion_status]
        return res[offset : offset + limit], len(res)


class FakeContentUnitOfWork:
    def __init__(self) -> None:
        self.sources = InMemoryContentSourceRepo()
        self.assets = InMemoryContentAssetRepo()


@pytest.mark.asyncio
async def test_revoke_and_query_handlers() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    revoke_handler = RevokeContentAssetHandler(uow, bus)
    get_handler = GetContentAssetHandler(uow)
    find_hash_handler = FindAssetByHashHandler(uow)
    list_handler = ListContentAssetsHandler(uow)

    source = ContentSource.create(
        code="PLAT_CCMAS",
        name="National Benchmark",
        source_type=ContentSourceType.CCMAS,
        authority_level=AuthorityLevel.REGULATORY,
        visibility=VisibilityScope.PLATFORM,
        created_by="admin",
        created_by_email="admin@build.internal",
    )
    await uow.sources.save_source(source)

    sha = "9" * 64
    # A platform asset written at system level (no HTTP route creates one).
    asset = ContentAsset.create(
        source_id=source.id,
        tenant_id=None,
        file_name="CCMAS_CS.pdf",
        mime_type="application/pdf",
        file_size_bytes=5000,
        content_sha256=sha,
        storage_uri="s3://b/ccmas.pdf",
        created_by="admin",
        created_by_email="admin@build.internal",
    )
    await uow.assets.save_asset(asset)

    # Query by ID and by Hash
    found_by_id = await get_handler.handle(GetContentAssetQuery(asset_id=asset.id))
    assert found_by_id is not None
    assert found_by_id.id == asset.id

    found_by_hash = await find_hash_handler.handle(FindAssetByHashQuery(content_sha256=sha))
    assert found_by_hash is not None
    assert found_by_hash.id == asset.id

    # List query
    items, total = await list_handler.handle(ListContentAssetsQuery(source_id=source.id))
    assert total == 1
    assert items[0].id == asset.id

    # Revoke
    revoked = await revoke_handler.handle(
        RevokeContentAssetCommand(asset_id=asset.id, reason="Superseded by new release", revoked_by="admin")
    )
    assert revoked.status == AssetStatus.REVOKED

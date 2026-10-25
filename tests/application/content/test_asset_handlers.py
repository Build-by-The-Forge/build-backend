import pytest

from app.application.content.access import ContentNotFoundError
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
async def test_register_and_deduplicate_asset() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    handler = RegisterContentAssetHandler(uow, bus)

    # 1. Seed ContentSource
    source = ContentSource.create(
        code="CSC201_NOTES",
        name="CSC201 Notes",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-1",
        created_by_email="usr1@futa.edu.ng",
        tenant_id="tenant-futa",
    )
    await uow.sources.save_source(source)

    sha_sample = "a" * 64

    # 2. First upload: Brand new asset -> is_deduplicated=False
    cmd1 = RegisterContentAssetCommand(
        source_id=source.id,
        tenant_id="tenant-futa",
        file_name="Lecture_01.pdf",
        mime_type="application/pdf",
        file_size_bytes=2048,
        content_sha256=sha_sample,
        storage_uri="s3://bucket/tenant-futa/lecture1.pdf",
        created_by="usr-1",
        created_by_email="usr1@futa.edu.ng",
    )
    asset1, dedup1 = await handler.handle(cmd1)
    assert dedup1 is False
    assert asset1.content_sha256 == sha_sample
    assert len(uow.assets.assets) == 1

    # 3. Second upload with same bytes -> is_deduplicated=True, returns asset1
    cmd2 = RegisterContentAssetCommand(
        source_id=source.id,
        tenant_id="tenant-futa",
        file_name="Lecture_01_Copy.pdf",
        mime_type="application/pdf",
        file_size_bytes=2048,
        content_sha256=sha_sample,
        storage_uri="s3://bucket/tenant-futa/lecture1_copy.pdf",
        created_by="usr-2",
        created_by_email="usr2@futa.edu.ng",
    )
    asset2, dedup2 = await handler.handle(cmd2)
    assert dedup2 is True
    assert asset2.id == asset1.id
    assert len(uow.assets.assets) == 1  # No duplicate created in store


@pytest.mark.asyncio
async def test_register_asset_validations() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    handler = RegisterContentAssetHandler(uow, bus)

    # Source does not exist: the same typed answer as another tenant's source
    with pytest.raises(ContentNotFoundError, match="source not found"):
        await handler.handle(
            RegisterContentAssetCommand(
                source_id="nonexistent",
                tenant_id="t1",
                file_name="doc.pdf",
                mime_type="application/pdf",
                file_size_bytes=100,
                content_sha256="b" * 64,
                storage_uri="s3://uri",
                created_by="u1",
                created_by_email="u1@test.com",
            )
        )

    # Revoked source
    revoked_source = ContentSource.create(
        code="REVOKED_SRC",
        name="Revoked",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="u1",
        created_by_email="u1@test.com",
        tenant_id="t1",
    )
    revoked_source.revoke("Decommissioned")
    await uow.sources.save_source(revoked_source)

    with pytest.raises(ValueError, match="Cannot register asset against revoked source"):
        await handler.handle(
            RegisterContentAssetCommand(
                source_id=revoked_source.id,
                tenant_id="t1",
                file_name="doc.pdf",
                mime_type="application/pdf",
                file_size_bytes=100,
                content_sha256="b" * 64,
                storage_uri="s3://uri",
                created_by="u1",
                created_by_email="u1@test.com",
            )
        )


@pytest.mark.asyncio
async def test_create_asset_version_handler() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    reg_handler = RegisterContentAssetHandler(uow, bus)
    ver_handler = CreateAssetVersionHandler(uow, bus)

    source = ContentSource.create(
        code="CSC201_SLIDES",
        name="CSC201 Slides",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="u1",
        created_by_email="u1@test.com",
        tenant_id="t1",
    )
    await uow.sources.save_source(source)

    v1, _ = await reg_handler.handle(
        RegisterContentAssetCommand(
            source_id=source.id,
            tenant_id="t1",
            file_name="slides_v1.pdf",
            mime_type="application/pdf",
            file_size_bytes=1000,
            content_sha256="1" * 64,
            storage_uri="s3://b/v1.pdf",
            created_by="u1",
            created_by_email="u1@test.com",
        )
    )

    # Create v2 edition
    v2 = await ver_handler.handle(
        CreateAssetVersionCommand(
            parent_asset_id=v1.id,
            file_name="slides_v2.pdf",
            mime_type="application/pdf",
            file_size_bytes=1500,
            content_sha256="2" * 64,
            storage_uri="s3://b/v2.pdf",
            created_by="u1",
            created_by_email="u1@test.com",
        )
    )

    assert v2.asset_version == 2
    assert v2.parent_asset_id == v1.id
    assert v2.status == AssetStatus.ACTIVE

    v1_updated = await uow.assets.get_asset_by_id(v1.id)
    assert v1_updated is not None
    assert v1_updated.status == AssetStatus.SUPERSEDED


@pytest.mark.asyncio
async def test_revoke_and_query_handlers() -> None:
    uow = FakeContentUnitOfWork()
    bus = EventBus()
    reg_handler = RegisterContentAssetHandler(uow, bus)
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
    asset, _ = await reg_handler.handle(
        RegisterContentAssetCommand(
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
    )

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

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import (
    AssetStatus,
    AuthorityLevel,
    ContentSourceType,
    IngestionStatus,
    VisibilityScope,
)
from app.domain.content.source import ContentSource
from app.infrastructure.content.asset_repositories import (
    SqlAlchemyContentAssetRepository,
)
from app.infrastructure.content.repositories import SqlAlchemyContentSourceRepository


@pytest.mark.asyncio
async def test_content_asset_persistence_round_trip(session: AsyncSession) -> None:
    source_repo = SqlAlchemyContentSourceRepository(session)
    asset_repo = SqlAlchemyContentAssetRepository(session)

    source = ContentSource.create(
        code=f"SRC_PERSIST_{uuid4().hex[:6].upper()}",
        name="CSC301 Data Structures",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
        tenant_id="tenant-futa",
    )
    await source_repo.save_source(source)

    sha = "e" * 64
    asset = ContentAsset.create(
        source_id=source.id,
        tenant_id="tenant-futa",
        file_name="trees_and_graphs.pdf",
        mime_type="application/pdf",
        file_size_bytes=1048576,
        content_sha256=sha,
        storage_uri="s3://build-content/tenants/futa/assets/trees.pdf",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
        metadata={"num_pages": 42, "ocr_candidate": True},
    )
    await asset_repo.save_asset(asset)

    # 1. Retrieve by ID
    retrieved = await asset_repo.get_asset_by_id(asset.id)
    assert retrieved is not None
    assert retrieved.id == asset.id
    assert retrieved.source_id == source.id
    assert retrieved.tenant_id == "tenant-futa"
    assert retrieved.file_name == "trees_and_graphs.pdf"
    assert retrieved.mime_type == "application/pdf"
    assert retrieved.file_size_bytes == 1048576
    assert retrieved.content_sha256 == sha
    assert retrieved.storage_uri == "s3://build-content/tenants/futa/assets/trees.pdf"
    assert retrieved.asset_version == 1
    assert retrieved.status == AssetStatus.ACTIVE
    assert retrieved.ingestion_status == IngestionStatus.UPLOADED
    assert retrieved.metadata["num_pages"] == 42

    # 2. Retrieve by Hash in Tenant Scope
    by_hash = await asset_repo.get_asset_by_hash(sha, "tenant-futa")
    assert by_hash is not None
    assert by_hash.id == asset.id

    # 3. Hash lookup in another tenant returns None
    other_tenant_lookup = await asset_repo.get_asset_by_hash(sha, "tenant-unilag")
    assert other_tenant_lookup is None

    # 4. List assets by source
    by_source, total = await asset_repo.list_assets_by_source(source.id)
    assert total == 1
    assert by_source[0].id == asset.id


@pytest.mark.asyncio
async def test_content_asset_db_unique_constraint(session: AsyncSession) -> None:
    source_repo = SqlAlchemyContentSourceRepository(session)
    asset_repo = SqlAlchemyContentAssetRepository(session)

    source = ContentSource.create(
        code=f"SRC_CONSTR_{uuid4().hex[:6].upper()}",
        name="Source Constraint Test",
        source_type=ContentSourceType.LECTURER_UPLOAD,
        authority_level=AuthorityLevel.INSTITUTIONAL,
        visibility=VisibilityScope.TENANT,
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
        tenant_id="tenant-futa",
    )
    await source_repo.save_source(source)

    sha = "f" * 64

    asset1 = ContentAsset.create(
        source_id=source.id,
        tenant_id="tenant-futa",
        file_name="first_file.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        content_sha256=sha,
        storage_uri="s3://b/futa/first.pdf",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
    )
    await asset_repo.save_asset(asset1)
    await session.commit()

    # Second asset with identical (tenant_id, content_sha256) violates unique constraint
    asset2 = ContentAsset.create(
        source_id=source.id,
        tenant_id="tenant-futa",
        file_name="second_file.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        content_sha256=sha,
        storage_uri="s3://b/futa/second.pdf",
        created_by="usr-lecturer",
        created_by_email="lecturer@futa.edu.ng",
    )
    with pytest.raises(IntegrityError):
        await asset_repo.save_asset(asset2)
        await session.commit()

    await session.rollback()

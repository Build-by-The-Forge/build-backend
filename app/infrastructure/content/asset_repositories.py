from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus
from app.domain.repositories.content_asset import ContentAssetRepository
from app.infrastructure.content.asset_mappers import (
    content_asset_model_to_domain,
    content_asset_to_model,
)
from app.infrastructure.db.models.content import ContentAssetModel


class SqlAlchemyContentAssetRepository(ContentAssetRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_asset(self, asset: ContentAsset) -> ContentAsset:
        stmt = select(ContentAssetModel).where(ContentAssetModel.id == asset.id)
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()

        if model is None:
            model = content_asset_to_model(asset)
            self._session.add(model)
        else:
            model = content_asset_to_model(asset, model)

        await self._session.flush()
        return content_asset_model_to_domain(model)

    async def insert_asset(self, asset: ContentAsset) -> ContentAsset:
        # Never a select-then-update: a concurrent insert of the same id must
        # reach the database and fail on its primary key (P3-1 PR 2 uploads).
        model = content_asset_to_model(asset)
        self._session.add(model)
        await self._session.flush()
        return content_asset_model_to_domain(model)

    async def get_asset_by_id(self, asset_id: str) -> ContentAsset | None:
        stmt = select(ContentAssetModel).where(ContentAssetModel.id == asset_id)
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return content_asset_model_to_domain(model) if model else None

    async def get_asset_by_hash(self, content_sha256: str, tenant_id: str | None = None) -> ContentAsset | None:
        clean_sha = content_sha256.strip().lower()
        if tenant_id is None:
            stmt = select(ContentAssetModel).where(
                ContentAssetModel.content_sha256 == clean_sha,
                ContentAssetModel.tenant_id.is_(None),
            )
        else:
            stmt = select(ContentAssetModel).where(
                ContentAssetModel.content_sha256 == clean_sha,
                ContentAssetModel.tenant_id == tenant_id,
            )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return content_asset_model_to_domain(model) if model else None

    async def list_assets_by_source(self, source_id: str, limit: int = 50, offset: int = 0) -> tuple[list[ContentAsset], int]:
        base = select(ContentAssetModel).where(ContentAssetModel.source_id == source_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            base.order_by(
                ContentAssetModel.asset_version.desc(),
                ContentAssetModel.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [content_asset_model_to_domain(m) for m in models], total

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
        stmt = select(ContentAssetModel)

        if tenant_id is not None:
            if include_platform:
                stmt = stmt.where(
                    or_(
                        ContentAssetModel.tenant_id == tenant_id,
                        ContentAssetModel.tenant_id.is_(None),
                    )
                )
            else:
                stmt = stmt.where(ContentAssetModel.tenant_id == tenant_id)
        else:
            if not include_platform:
                stmt = stmt.where(ContentAssetModel.tenant_id.is_not(None))

        if source_id is not None:
            stmt = stmt.where(ContentAssetModel.source_id == source_id)
        if status is not None:
            stmt = stmt.where(ContentAssetModel.status == status.value)
        if ingestion_status is not None:
            stmt = stmt.where(ContentAssetModel.ingestion_status == ingestion_status.value)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(ContentAssetModel.created_at.desc()).limit(limit).offset(offset)
        models = (await self._session.execute(stmt)).scalars().all()
        return [content_asset_model_to_domain(m) for m in models], total

"""The read policy in SQL (M3-D ruling B): ``readable(reader)`` is
``app.application.content.read_policy.may_read`` as a predicate on
``content_assets``, so a list's page and total only ever count what the
caller may read. tests/integration/content/test_read_policy.py checks that
the two agree on every row of the design's table."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import ColumnElement, and_, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application.content.read_policy import UNCLEAN_INGESTION, UNREADABLE_STATUSES, Reader
from app.db.session import SessionLocal
from app.domain.content.asset import ContentAsset
from app.domain.content.enums import AssetStatus, IngestionStatus
from app.domain.content.job import ContentIngestionJob
from app.infrastructure.content.asset_mappers import content_asset_model_to_domain
from app.infrastructure.content.job_mappers import content_job_model_to_domain
from app.infrastructure.db.models.content import (
    ContentAssetModel,
    ContentIngestionJobModel,
    ContentPublicationModel,
    ContentRightsAssertionModel,
)


def _published() -> ColumnElement[bool]:
    return (
        select(ContentPublicationModel.id)
        .where(
            ContentPublicationModel.asset_id == ContentAssetModel.id,
            ContentPublicationModel.tenant_id == ContentAssetModel.tenant_id,
            ContentPublicationModel.state == "published",
            ContentPublicationModel.hidden_at.is_(None),
        )
        .exists()
    )


def _reviewed_for_students() -> ColumnElement[bool]:
    # The latest staff review, by (asserted_at, id), accepted it for the tenant.
    review = aliased(ContentRightsAssertionModel)
    later = aliased(ContentRightsAssertionModel)
    later_review = (
        select(later.id)
        .where(
            later.asset_id == review.asset_id,
            later.tenant_id == review.tenant_id,
            later.kind == "staff_review",
            or_(
                later.asserted_at > review.asserted_at,
                and_(later.asserted_at == review.asserted_at, later.id > review.id),
            ),
        )
        .exists()
    )
    return (
        select(review.id)
        .where(
            review.asset_id == ContentAssetModel.id,
            review.tenant_id == ContentAssetModel.tenant_id,
            review.kind == "staff_review",
            review.outcome == "accepted",
            review.audience == "tenant",
            ~later_review,
        )
        .exists()
    )


def readable(reader: Reader) -> ColumnElement[bool]:
    """``may_read`` for every row of ``content_assets``, in the same order."""
    staff = true() if reader.manages_shared else false()
    in_tenant = ContentAssetModel.tenant_id == reader.tenant_id
    personal = and_(
        ContentAssetModel.ownership_class == "personal",
        or_(
            ContentAssetModel.owner_user_id == reader.user_id,
            and_(_published(), ContentAssetModel.ingestion_status.not_in(sorted(UNCLEAN_INGESTION))),
        ),
    )
    institutional = and_(ContentAssetModel.ownership_class == "institutional", or_(staff, _reviewed_for_students()))
    other_class = and_(ContentAssetModel.ownership_class.not_in(("personal", "institutional")), staff)
    return and_(
        ContentAssetModel.status.not_in(sorted(UNREADABLE_STATUSES)),
        or_(
            and_(ContentAssetModel.tenant_id.is_(None), staff),
            and_(in_tenant, or_(personal, institutional, other_class)),
        ),
    )


class SqlAlchemyContentReadRepository:
    """``ContentReadPort``: every query filters by ``readable`` in SQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def readable_asset_ids(self, reader: Reader, asset_ids: set[str]) -> set[str]:
        statement = select(ContentAssetModel.id).where(ContentAssetModel.id.in_(sorted(asset_ids)), readable(reader))
        return set((await self._session.execute(statement)).scalars().all())

    async def list_assets(
        self,
        reader: Reader,
        *,
        source_id: str | None,
        status: AssetStatus | None,
        ingestion_status: IngestionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContentAsset], int]:
        conditions = [readable(reader)]
        if source_id is not None:
            conditions.append(ContentAssetModel.source_id == source_id)
        if status is not None:
            conditions.append(ContentAssetModel.status == status.value)
        if ingestion_status is not None:
            conditions.append(ContentAssetModel.ingestion_status == ingestion_status.value)
        total = (await self._session.execute(select(func.count(ContentAssetModel.id)).where(*conditions))).scalar_one()
        statement = (
            select(ContentAssetModel)
            .where(*conditions)
            .order_by(ContentAssetModel.created_at.desc(), ContentAssetModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [content_asset_model_to_domain(model) for model in models], int(total)

    async def list_jobs(
        self,
        reader: Reader,
        *,
        asset_id: str | None,
        source_id: str | None,
        status: IngestionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContentIngestionJob], int]:
        # A job is readable when its document is.
        conditions = [
            ContentIngestionJobModel.asset_id.in_(select(ContentAssetModel.id).where(readable(reader))),
        ]
        if asset_id is not None:
            conditions.append(ContentIngestionJobModel.asset_id == asset_id)
        if source_id is not None:
            conditions.append(ContentIngestionJobModel.source_id == source_id)
        if status is not None:
            conditions.append(ContentIngestionJobModel.status == status.value)
        total = (await self._session.execute(select(func.count(ContentIngestionJobModel.id)).where(*conditions))).scalar_one()
        statement = (
            select(ContentIngestionJobModel)
            .where(*conditions)
            .order_by(
                ContentIngestionJobModel.created_at.desc(),
                ContentIngestionJobModel.run_number.desc(),
                ContentIngestionJobModel.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [content_job_model_to_domain(model) for model in models], int(total)

    async def get_job(self, reader: Reader, job_id: str) -> ContentIngestionJob | None:
        statement = select(ContentIngestionJobModel).where(
            ContentIngestionJobModel.id == job_id,
            ContentIngestionJobModel.asset_id.in_(select(ContentAssetModel.id).where(readable(reader))),
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return content_job_model_to_domain(model) if model is not None else None


@asynccontextmanager
async def content_read_port() -> AsyncIterator[SqlAlchemyContentReadRepository]:
    async with SessionLocal() as session:
        yield SqlAlchemyContentReadRepository(session)

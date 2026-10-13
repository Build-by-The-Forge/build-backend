from __future__ import annotations

from datetime import datetime, timezone

from app.domain.content.enums import IngestionStatus
from app.domain.content.ingestion_event import IngestionEventRecord
from app.domain.content.job import CallbackOutcome, ContentIngestionJob
from app.domain.repositories.content_job import ContentIngestionJobRepository
from app.infrastructure.content.job_mappers import (
    content_job_model_to_domain,
    content_job_to_model,
)
from app.infrastructure.db.models.content import (
    ContentIngestionEventModel,
    ContentIngestionJobModel,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyContentIngestionJobRepository(ContentIngestionJobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_job(self, job: ContentIngestionJob) -> ContentIngestionJob:
        stmt = select(ContentIngestionJobModel).where(
            ContentIngestionJobModel.id == job.id
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()

        if model is None:
            model = content_job_to_model(job)
            self._session.add(model)
        else:
            model = content_job_to_model(job, model)

        await self._session.flush()
        return content_job_model_to_domain(model)

    async def get_job_by_id(self, job_id: str) -> ContentIngestionJob | None:
        stmt = select(ContentIngestionJobModel).where(
            ContentIngestionJobModel.id == job_id
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return content_job_model_to_domain(model) if model else None

    async def get_job_for_update(self, job_id: str) -> ContentIngestionJob | None:
        # SELECT ... FOR UPDATE on PostgreSQL; SQLite ignores the lock.
        stmt = (
            select(ContentIngestionJobModel)
            .where(ContentIngestionJobModel.id == job_id)
            .with_for_update()
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return content_job_model_to_domain(model) if model else None

    async def get_latest_job_for_asset(
        self, asset_id: str
    ) -> ContentIngestionJob | None:
        stmt = (
            select(ContentIngestionJobModel)
            .where(ContentIngestionJobModel.asset_id == asset_id)
            .order_by(
                ContentIngestionJobModel.run_number.desc(),
                ContentIngestionJobModel.created_at.desc(),
            )
            .limit(1)
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return content_job_model_to_domain(model) if model else None

    async def list_jobs_for_asset(
        self, asset_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ContentIngestionJob], int]:
        base = select(ContentIngestionJobModel).where(
            ContentIngestionJobModel.asset_id == asset_id
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            base.order_by(
                ContentIngestionJobModel.run_number.desc(),
                ContentIngestionJobModel.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [content_job_model_to_domain(m) for m in models], total

    async def list_pending_jobs(
        self, tenant_id: str | None = None, limit: int = 50
    ) -> list[ContentIngestionJob]:
        now = datetime.now(timezone.utc)
        stmt = select(ContentIngestionJobModel).where(
            or_(
                ContentIngestionJobModel.status == IngestionStatus.QUEUED.value,
                (
                    (ContentIngestionJobModel.status == IngestionStatus.FAILED.value)
                    & (ContentIngestionJobModel.is_retryable.is_(True))
                    & (ContentIngestionJobModel.next_retry_at <= now)
                ),
            )
        )
        if tenant_id is not None:
            stmt = stmt.where(ContentIngestionJobModel.tenant_id == tenant_id)

        stmt = stmt.order_by(ContentIngestionJobModel.created_at.asc()).limit(limit)
        models = (await self._session.execute(stmt)).scalars().all()
        return [content_job_model_to_domain(m) for m in models]

    async def list_jobs(
        self,
        tenant_id: str | None = None,
        asset_id: str | None = None,
        source_id: str | None = None,
        status: IngestionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentIngestionJob], int]:
        stmt = select(ContentIngestionJobModel)

        if tenant_id is not None:
            stmt = stmt.where(
                or_(
                    ContentIngestionJobModel.tenant_id == tenant_id,
                    ContentIngestionJobModel.tenant_id.is_(None),
                )
            )
        if asset_id is not None:
            stmt = stmt.where(ContentIngestionJobModel.asset_id == asset_id)
        if source_id is not None:
            stmt = stmt.where(ContentIngestionJobModel.source_id == source_id)
        if status is not None:
            stmt = stmt.where(ContentIngestionJobModel.status == status.value)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(ContentIngestionJobModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [content_job_model_to_domain(m) for m in models], total


class SqlAlchemyIngestionEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: str) -> IngestionEventRecord | None:
        model = await self._session.get(ContentIngestionEventModel, event_id)
        if model is None:
            return None
        return IngestionEventRecord(
            event_id=model.event_id,
            job_id=model.job_id,
            tenant_id=model.tenant_id,
            run_number=model.run_number,
            attempt_count=model.attempt_count,
            external_task_id=model.external_task_id,
            event_type=model.event_type,
            stage=model.stage,
            payload_sha256=model.payload_sha256,
            outcome=CallbackOutcome(model.outcome),
            received_at=model.received_at,
        )

    async def add(self, record: IngestionEventRecord) -> None:
        self._session.add(
            ContentIngestionEventModel(
                event_id=record.event_id,
                job_id=record.job_id,
                tenant_id=record.tenant_id,
                run_number=record.run_number,
                attempt_count=record.attempt_count,
                external_task_id=record.external_task_id,
                event_type=record.event_type,
                stage=record.stage,
                payload_sha256=record.payload_sha256,
                outcome=record.outcome.value,
                received_at=record.received_at,
            )
        )
        await self._session.flush()

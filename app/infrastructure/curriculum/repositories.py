from __future__ import annotations

from app.domain.curriculum.source import CurriculumSnapshot, CurriculumSource
from app.domain.repositories.curriculum_source import CurriculumSourceRepository
from app.infrastructure.curriculum.mappers import (
    curriculum_snapshot_model_to_domain,
    curriculum_snapshot_to_model,
    curriculum_source_model_to_domain,
    curriculum_source_to_model,
)
from app.infrastructure.db.models.curriculum import (
    CurriculumSnapshotModel,
    CurriculumSourceModel,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyCurriculumSourceRepository(CurriculumSourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_source(self, source: CurriculumSource) -> CurriculumSource:
        statement = select(CurriculumSourceModel).where(
            CurriculumSourceModel.id == source.id
        )
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = curriculum_source_to_model(source)
            self._session.add(model)
        else:
            curriculum_source_to_model(source, model=model)
        await self._session.flush()
        return source

    async def get_source_by_id(self, source_id: str) -> CurriculumSource | None:
        statement = select(CurriculumSourceModel).where(
            CurriculumSourceModel.id == source_id
        )
        model = (await self._session.scalars(statement)).first()
        return curriculum_source_model_to_domain(model) if model is not None else None

    async def get_source_by_code(self, code: str) -> CurriculumSource | None:
        statement = select(CurriculumSourceModel).where(
            CurriculumSourceModel.code == code.upper()
        )
        model = (await self._session.scalars(statement)).first()
        return curriculum_source_model_to_domain(model) if model is not None else None

    async def list_sources(self, status: str | None = None) -> list[CurriculumSource]:
        statement = select(CurriculumSourceModel).order_by(
            CurriculumSourceModel.code.asc()
        )
        if status is not None:
            statement = statement.where(CurriculumSourceModel.status == status)
        models = (await self._session.scalars(statement)).all()
        return [curriculum_source_model_to_domain(model) for model in models]

    async def save_snapshot(self, snapshot: CurriculumSnapshot) -> CurriculumSnapshot:
        statement = select(CurriculumSnapshotModel).where(
            CurriculumSnapshotModel.id == snapshot.id
        )
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = curriculum_snapshot_to_model(snapshot)
            self._session.add(model)
        else:
            model.status = snapshot.status.value
        await self._session.flush()
        return snapshot

    async def get_latest_snapshot(self, source_id: str) -> CurriculumSnapshot | None:
        statement = (
            select(CurriculumSnapshotModel)
            .where(CurriculumSnapshotModel.source_id == source_id)
            .order_by(CurriculumSnapshotModel.retrieved_at.desc())
            .limit(1)
        )
        model = (await self._session.scalars(statement)).first()
        return curriculum_snapshot_model_to_domain(model) if model is not None else None

    async def get_snapshot_by_hash(
        self, source_id: str, content_sha256: str
    ) -> CurriculumSnapshot | None:
        statement = select(CurriculumSnapshotModel).where(
            CurriculumSnapshotModel.source_id == source_id,
            CurriculumSnapshotModel.content_sha256 == content_sha256.lower(),
        )
        model = (await self._session.scalars(statement)).first()
        return curriculum_snapshot_model_to_domain(model) if model is not None else None

    async def list_snapshots(
        self, source_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[CurriculumSnapshot], int]:
        count_stmt = (
            select(func.count())
            .select_from(CurriculumSnapshotModel)
            .where(CurriculumSnapshotModel.source_id == source_id)
        )
        total = (await self._session.scalar(count_stmt)) or 0

        statement = (
            select(CurriculumSnapshotModel)
            .where(CurriculumSnapshotModel.source_id == source_id)
            .order_by(CurriculumSnapshotModel.retrieved_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = (await self._session.scalars(statement)).all()
        return [curriculum_snapshot_model_to_domain(m) for m in models], total

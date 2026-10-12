from __future__ import annotations

from app.domain.curriculum.audit import (
    BenchmarkAuditAction,
    BenchmarkAuditLog,
)
from app.domain.repositories.benchmark_audit import BenchmarkAuditRepository
from app.infrastructure.db.models.benchmark_audit import BenchmarkAuditLogModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _model_to_domain(model: BenchmarkAuditLogModel) -> BenchmarkAuditLog:
    return BenchmarkAuditLog(
        id=model.id,
        curriculum_id=model.curriculum_id,
        action=BenchmarkAuditAction(model.action),
        actor_id=model.actor_id,
        actor_email=model.actor_email,
        previous_status=model.previous_status,
        new_status=model.new_status,
        reason=model.reason,
        review_notes=model.review_notes,
        diff_fingerprint=model.diff_fingerprint,
        metadata_payload=model.metadata_json or {},
        created_at=model.created_at,
    )


class SqlAlchemyBenchmarkAuditRepository(BenchmarkAuditRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, log: BenchmarkAuditLog) -> BenchmarkAuditLog:
        model = BenchmarkAuditLogModel(
            id=log.id,
            curriculum_id=log.curriculum_id,
            action=log.action.value,
            actor_id=log.actor_id,
            actor_email=log.actor_email,
            previous_status=log.previous_status,
            new_status=log.new_status,
            reason=log.reason,
            review_notes=log.review_notes,
            diff_fingerprint=log.diff_fingerprint,
            metadata_json=log.metadata_payload,
            created_at=log.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return log

    async def list_by_curriculum(self, curriculum_id: str) -> list[BenchmarkAuditLog]:
        statement = (
            select(BenchmarkAuditLogModel)
            .where(BenchmarkAuditLogModel.curriculum_id == curriculum_id)
            .order_by(BenchmarkAuditLogModel.created_at.asc())
        )
        models = (await self._session.scalars(statement)).all()
        return [_model_to_domain(m) for m in models]

    async def list_recent(self, limit: int = 50, action: str | None = None) -> list[BenchmarkAuditLog]:
        statement = select(BenchmarkAuditLogModel).order_by(BenchmarkAuditLogModel.created_at.desc())
        if action is not None:
            statement = statement.where(BenchmarkAuditLogModel.action == action)
        statement = statement.limit(limit)
        models = (await self._session.scalars(statement)).all()
        return [_model_to_domain(m) for m in models]

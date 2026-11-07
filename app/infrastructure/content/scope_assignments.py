"""The scope-assignment outbox (M3-D PR 5, migration 0031).

A row is written in the same transaction as the decision behind it, and the
caller holds the document's row lock, so versions rise one at a time per
document. The dispatcher delivers pending rows, lowerings first; a row is
settled only when the AI service returns its version (acknowledged) or a
higher one (superseded). A tenant's pending lowerings are the
``denied_assets`` every retrieving call carries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.content import ContentAssetModel, ContentScopeAssignmentModel

INSTITUTIONAL = "institutional"
SCOPES = frozenset({"institutional", "personal", "unknown"})


@dataclass(frozen=True, slots=True)
class ScopeAssignment:
    id: str
    tenant_id: str
    asset_id: str
    scope: str
    version: int
    lowers: bool
    attempts: int
    created_at: datetime


def _row(model: ContentScopeAssignmentModel) -> ScopeAssignment:
    return ScopeAssignment(
        id=model.id,
        tenant_id=model.tenant_id,
        asset_id=model.asset_id,
        scope=model.scope,
        version=model.version,
        lowers=model.lowers,
        attempts=model.attempts,
        created_at=model.created_at,
    )


class SqlAlchemyScopeAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_scope(self, tenant_id: str, asset_id: str) -> str | None:
        """The scope most recently decided for the document, delivered or not."""
        statement = (
            select(ContentScopeAssignmentModel.scope)
            .where(ContentScopeAssignmentModel.tenant_id == tenant_id, ContentScopeAssignmentModel.asset_id == asset_id)
            .order_by(ContentScopeAssignmentModel.version.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def enqueue(self, *, tenant_id: str, asset_id: str, scope: str, reason: str, decided_by: str) -> ScopeAssignment:
        """Queue the document's next version, in the transaction that records
        the decision. The document's row is locked first, so two decisions
        on one document take consecutive versions, never the same one."""
        if scope not in SCOPES:
            raise ValueError(f"unknown scope {scope!r}")
        await self._session.execute(
            select(ContentAssetModel.id)
            .where(ContentAssetModel.id == asset_id, ContentAssetModel.tenant_id == tenant_id)
            .with_for_update()
        )
        current = (
            await self._session.execute(
                select(func.max(ContentScopeAssignmentModel.version)).where(
                    ContentScopeAssignmentModel.tenant_id == tenant_id, ContentScopeAssignmentModel.asset_id == asset_id
                )
            )
        ).scalar_one()
        model = ContentScopeAssignmentModel(
            id=str(uuid4()),
            tenant_id=tenant_id,
            asset_id=asset_id,
            scope=scope,
            version=(current or 0) + 1,
            lowers=scope != INSTITUTIONAL,
            reason=reason,
            decided_by=decided_by,
            state="pending",
            attempts=0,
            next_attempt_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        return _row(model)

    async def pending_lowerings(self, tenant_id: str) -> frozenset[str]:
        """The tenant's denied_assets: documents lowered and not yet acknowledged."""
        statement = select(ContentScopeAssignmentModel.asset_id).where(
            ContentScopeAssignmentModel.tenant_id == tenant_id,
            ContentScopeAssignmentModel.state == "pending",
            ContentScopeAssignmentModel.lowers.is_(True),
        )
        return frozenset((await self._session.execute(statement)).scalars().all())

    async def claim_due(self, excluded_ids: set[str]) -> ScopeAssignment | None:
        """The next pending row that is due, lowerings first, locked so no
        other dispatcher takes it in this transaction."""
        statement = (
            select(ContentScopeAssignmentModel)
            .where(
                ContentScopeAssignmentModel.state == "pending",
                ContentScopeAssignmentModel.next_attempt_at <= datetime.now(timezone.utc),
            )
            .order_by(
                ContentScopeAssignmentModel.lowers.desc(),
                ContentScopeAssignmentModel.next_attempt_at.asc(),
                ContentScopeAssignmentModel.id.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if excluded_ids:
            statement = statement.where(ContentScopeAssignmentModel.id.not_in(excluded_ids))
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return _row(model) if model is not None else None

    async def settle(self, assignment: ScopeAssignment, stored_version: int) -> str:
        """The AI service now holds ``stored_version`` for the document. Every
        pending row of that document at or below it is settled: its own
        version acknowledged, lower ones superseded."""
        now = datetime.now(timezone.utc)
        same = (
            ContentScopeAssignmentModel.tenant_id == assignment.tenant_id,
            ContentScopeAssignmentModel.asset_id == assignment.asset_id,
            ContentScopeAssignmentModel.state == "pending",
        )
        await self._session.execute(
            update(ContentScopeAssignmentModel)
            .where(*same, ContentScopeAssignmentModel.version == stored_version)
            .values(state="acknowledged", settled_at=now, last_error_code=None)
        )
        await self._session.execute(
            update(ContentScopeAssignmentModel)
            .where(*same, ContentScopeAssignmentModel.version < stored_version)
            .values(state="superseded", settled_at=now)
        )
        return "acknowledged" if stored_version == assignment.version else "superseded"

    async def record_failure(self, assignment: ScopeAssignment, error_code: str, delay_seconds: int) -> None:
        """Still pending: retried after the delay. Nothing is assumed delivered."""
        await self._session.execute(
            update(ContentScopeAssignmentModel)
            .where(ContentScopeAssignmentModel.id == assignment.id, ContentScopeAssignmentModel.state == "pending")
            .values(
                attempts=ContentScopeAssignmentModel.attempts + 1,
                last_error_code=error_code[:64],
                next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
            )
        )

    async def backlog(self) -> list[tuple[bool, int, datetime | None]]:
        """(lowers, pending count, oldest created_at) for the age alerts."""
        statement = (
            select(
                ContentScopeAssignmentModel.lowers,
                func.count(ContentScopeAssignmentModel.id),
                func.min(ContentScopeAssignmentModel.created_at),
            )
            .where(ContentScopeAssignmentModel.state == "pending")
            .group_by(ContentScopeAssignmentModel.lowers)
        )
        return [(bool(lowers), int(count), oldest) for lowers, count, oldest in (await self._session.execute(statement)).all()]

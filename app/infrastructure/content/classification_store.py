"""The classification service's store (M3-D PR 5): one transaction per use,
committed when the context exits cleanly and rolled back otherwise."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.content.classification import Decision, DocumentState
from app.core.authorization import ROLE_PERMISSIONS, Permission
from app.db.session import SessionLocal
from app.db.timeouts import set_transaction_timeouts
from app.infrastructure.content.scope_assignments import SqlAlchemyScopeAssignmentRepository
from app.infrastructure.db.models.content import (
    ContentAssetModel,
    ContentAuthorityAuthorizationModel,
    ContentClassificationRunModel,
    ContentOwnershipClassificationModel,
    ContentRightsAssertionModel,
    ContentSourceModel,
)
from app.infrastructure.db.models.tenant_core import MembershipModel

# The roles whose permissions include managing shared content: the same
# check a staff route makes through authorization.can.
CONTENT_ROLES = tuple(sorted(role for role, granted in ROLE_PERMISSIONS.items() if Permission.CONTENT_SOURCE_MANAGE in granted))


class SqlAlchemyClassificationStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authorization_valid(self, tenant_id: str, authorization_id: str, *, lock: bool = False) -> bool:
        """With ``lock``, the row is held FOR SHARE until the transaction ends: a
        concurrent revocation waits for this decision to commit, and a
        revocation committed first is seen here and refuses it."""
        now = datetime.now(timezone.utc)
        statement = select(ContentAuthorityAuthorizationModel.id).where(
            ContentAuthorityAuthorizationModel.id == authorization_id,
            ContentAuthorityAuthorizationModel.tenant_id == tenant_id,
            ContentAuthorityAuthorizationModel.revoked_at.is_(None),
            ContentAuthorityAuthorizationModel.granted_at <= now,
            or_(
                ContentAuthorityAuthorizationModel.expires_at.is_(None),
                ContentAuthorityAuthorizationModel.expires_at > now,
            ),
        )
        if lock:
            statement = statement.with_for_update(read=True)
        return await self._session.scalar(statement) is not None

    async def operator_manages_content(self, tenant_id: str, user_id: str, *, lock: bool = False) -> bool:
        statement = select(MembershipModel.id).where(
            MembershipModel.tenant_id == tenant_id,
            MembershipModel.user_id == user_id,
            MembershipModel.status == "active",
            MembershipModel.role.in_(CONTENT_ROLES),
        )
        if lock:
            statement = statement.with_for_update(read=True)
        return await self._session.scalar(statement) is not None

    async def document(self, tenant_id: str, asset_id: str, *, lock: bool) -> DocumentState | None:
        statement = (
            select(
                ContentAssetModel.tenant_id,
                ContentAssetModel.ownership_class,
                ContentAssetModel.owner_user_id,
                ContentAssetModel.status,
                ContentSourceModel.owner_user_id,
            )
            .join(ContentSourceModel, ContentSourceModel.id == ContentAssetModel.source_id)
            .where(ContentAssetModel.id == asset_id, ContentAssetModel.tenant_id == tenant_id)
        )
        if lock:
            statement = statement.with_for_update(of=ContentAssetModel)
        row = (await self._session.execute(statement)).first()
        if row is None:
            return None
        return DocumentState(
            tenant_id=tenant_id, ownership_class=row[1], owner_user_id=row[2], status=row[3], source_owner_user_id=row[4]
        )

    async def create_run(self, tenant_id: str, authorization_id: str, operator_user_id: str, requested: int) -> str:
        run_id = str(uuid4())
        self._session.add(
            ContentClassificationRunModel(
                id=run_id,
                tenant_id=tenant_id,
                authorization_id=authorization_id,
                operator_user_id=operator_user_id,
                requested=requested,
                started_at=datetime.now(timezone.utc),
            )
        )
        await self._session.flush()
        return run_id

    async def record(self, tenant_id: str, decision: Decision, operator_user_id: str, run_id: str) -> bool:
        now = datetime.now(timezone.utc)
        # The audit record: operator, tenant, asset, previous and new class,
        # evidence, time and run.
        self._session.add(
            ContentOwnershipClassificationModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                asset_id=decision.asset_id,
                previous_class="unclassified",
                new_class="institutional",
                decided_by=operator_user_id,
                decided_via="operator_command",
                evidence_reference=decision.evidence_reference,
                run_id=run_id,
                decided_at=now,
            )
        )
        await self._session.execute(
            update(ContentAssetModel)
            .where(
                ContentAssetModel.id == decision.asset_id,
                ContentAssetModel.tenant_id == tenant_id,
                ContentAssetModel.ownership_class == "unclassified",
            )
            .values(ownership_class="institutional", updated_at=now)
        )
        self._session.add(
            ContentRightsAssertionModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                asset_id=decision.asset_id,
                asserted_by=operator_user_id,
                kind="staff_review",
                rights_basis=decision.rights_basis,
                audience=decision.audience,
                redistribution=decision.redistribution,
                ai_use=decision.ai_use,
                outcome="accepted",
                reason=decision.evidence_reference,
                asserted_at=now,
            )
        )
        await self._session.flush()
        # Knowledge eligibility needs a review that permits AI use: only then
        # is the institutional scope queued for the AI service.
        if decision.ai_use != "permitted":
            return False
        await SqlAlchemyScopeAssignmentRepository(self._session).enqueue(
            tenant_id=tenant_id,
            asset_id=decision.asset_id,
            scope="institutional",
            reason="classified",
            decided_by=operator_user_id,
        )
        return True


@asynccontextmanager
async def classification_store() -> AsyncIterator[SqlAlchemyClassificationStore]:
    async with SessionLocal() as session:
        async with session.begin():
            if session.get_bind().dialect.name == "postgresql":
                await set_transaction_timeouts(session)
            yield SqlAlchemyClassificationStore(session)

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.user import Session
from app.domain.repositories.session import SessionRepository
from app.infrastructure.identity.mappers import (
    domain_session_to_model,
    session_model_to_domain,
)
from app.infrastructure.identity.models import SessionModel


class SQLAlchemySessionRepository(SessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, session: Session) -> Session:
        model = await self._find_by_id(session.id.value)
        if model is None:
            model = domain_session_to_model(session)
            self._session.add(model)
        else:
            model = domain_session_to_model(session, model=model)
        await self._session.flush()
        return session_model_to_domain(model)

    async def get_by_id(self, session_id: str) -> Session | None:
        model = await self._find_by_id(session_id)
        return session_model_to_domain(model) if model is not None else None

    async def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        statement = select(SessionModel).where(
            SessionModel.refresh_token_hash == token_hash
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return session_model_to_domain(model) if model is not None else None

    async def list_active_by_user_id(self, user_id: str) -> list[Session]:
        statement = select(SessionModel).where(
            SessionModel.user_id == user_id,
            SessionModel.revoked_at.is_(None),
            or_(
                SessionModel.expires_at.is_(None),
                SessionModel.expires_at >= datetime.now(timezone.utc),
            ),
        )
        result = await self._session.scalars(statement)
        return [session_model_to_domain(model) for model in result.all()]

    async def revoke(self, session_id: str) -> None:
        statement = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self._session.execute(statement)

    async def revoke_all_for_user(self, user_id: str) -> list[str]:
        """Revoke every unrevoked session of the user; return their ids."""
        session_ids = list(
            await self._session.scalars(
                select(SessionModel.id).where(
                    SessionModel.user_id == user_id,
                    SessionModel.revoked_at.is_(None),
                )
            )
        )
        if session_ids:
            await self._session.execute(
                update(SessionModel)
                .where(SessionModel.id.in_(session_ids))
                .values(revoked_at=datetime.now(timezone.utc))
            )
        return session_ids

    async def _find_by_id(self, session_id: str) -> SessionModel | None:
        return await self._session.get(SessionModel, session_id)

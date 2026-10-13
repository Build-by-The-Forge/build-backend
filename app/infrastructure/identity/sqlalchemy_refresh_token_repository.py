from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.refresh_token import (
    RefreshTokenRepository,
    StoredRefreshToken,
)
from app.infrastructure.identity.models import RefreshTokenModel


class SQLAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session_id: str, token_hash: str, expires_at: datetime) -> None:
        self._session.add(
            RefreshTokenModel(
                id=str(uuid4()),
                session_id=session_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        model = await self._session.scalar(select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash))
        if model is None:
            return None
        return StoredRefreshToken(
            id=model.id,
            session_id=model.session_id,
            expires_at=model.expires_at,
            rotated_at=model.rotated_at,
            revoked_at=model.revoked_at,
        )

    async def consume(self, token_id: str) -> bool:
        result = await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.id == token_id,
                RefreshTokenModel.rotated_at.is_(None),
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(rotated_at=datetime.now(timezone.utc))
        )
        return result.rowcount == 1

    async def revoke_for_session(self, session_id: str) -> None:
        await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.session_id == session_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )

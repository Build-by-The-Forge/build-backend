from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.identity.sqlalchemy_refresh_token_repository import (
    SQLAlchemyRefreshTokenRepository,
)
from app.infrastructure.identity.sqlalchemy_session_repository import (
    SQLAlchemySessionRepository,
)
from app.infrastructure.identity.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.unit_of_work import UnitOfWork


class IdentityUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.users = SQLAlchemyUserRepository(session)
        self.sessions = SQLAlchemySessionRepository(session)
        self.refresh_tokens = SQLAlchemyRefreshTokenRepository(session)


@asynccontextmanager
async def identity_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[IdentityUnitOfWork]:
    async with IdentityUnitOfWork(session) as uow:
        yield uow

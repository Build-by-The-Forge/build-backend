from __future__ import annotations

from typing import Any

from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: Any) -> None:
        self._session = session

    async def save(self, user: User) -> User:
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.get(User, email)

    async def exists_by_email(self, email: str) -> bool:
        return await self._session.get(User, email) is not None

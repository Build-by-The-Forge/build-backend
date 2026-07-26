from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository
from app.infrastructure.identity.mappers import domain_user_to_model, user_model_to_domain
from app.infrastructure.identity.models import UserModel


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user: User) -> User:
        model = await self._find_by_id(user.id.value)
        if model is None:
            model = domain_user_to_model(user)
            self._session.add(model)
        else:
            model = domain_user_to_model(user, model=model)
        await self._session.flush()
        # Refresh the model to get eager-loaded relationships
        await self._session.refresh(model, ["roles"])
        return user_model_to_domain(model)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(UserModel).where(UserModel.email == email).options(selectinload(UserModel.roles))
        result = await self._session.scalars(statement)
        model = result.first()
        return user_model_to_domain(model) if model is not None else None

    async def exists_by_email(self, email: str) -> bool:
        statement = select(UserModel.id).where(UserModel.email == email)
        result = await self._session.scalars(statement)
        return result.first() is not None

    async def get_by_id(self, user_id: str) -> User | None:
        model = await self._find_by_id(user_id)
        return user_model_to_domain(model) if model is not None else None

    async def _find_by_id(self, user_id: str) -> UserModel | None:
        return await self._session.get(UserModel, user_id)

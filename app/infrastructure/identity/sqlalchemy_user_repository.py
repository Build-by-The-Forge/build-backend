from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository
from app.infrastructure.identity.mappers import domain_user_to_model, user_model_to_domain
from app.infrastructure.identity.models import PasswordResetTokenModel, UserModel


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

    async def save_password_reset_token(self, user_id: str, token_hash: str, expires_at: datetime | None = None) -> None:
        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        model = PasswordResetTokenModel(id=str(uuid4()), user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(model)
        await self._session.flush()

    async def consume_password_reset_token(self, token_hash: str) -> str | None:
        statement = select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.token_hash == token_hash,
            PasswordResetTokenModel.consumed_at.is_(None),
            or_(
                PasswordResetTokenModel.expires_at.is_(None),
                PasswordResetTokenModel.expires_at > datetime.now(timezone.utc),
            ),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            return None

        model.consumed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return model.user_id

    async def _find_by_id(self, user_id: str) -> UserModel | None:
        return await self._session.get(UserModel, user_id)

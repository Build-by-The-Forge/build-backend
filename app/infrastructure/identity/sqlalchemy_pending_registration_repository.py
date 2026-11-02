from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.pending_registration import PendingRegistration, PendingRegistrationRepository
from app.infrastructure.identity.models import PendingRegistrationModel


class SQLAlchemyPendingRegistrationRepository(PendingRegistrationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        email: str,
        password_hash: str,
        *,
        request_id: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self._session.add(
            PendingRegistrationModel(
                id=str(uuid4()),
                email=email,
                password_hash=password_hash,
                attempts=0,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self._session.flush()

    async def claim_next(self, excluded_ids: set[str]) -> PendingRegistration | None:
        statement = (
            select(PendingRegistrationModel)
            .order_by(PendingRegistrationModel.created_at, PendingRegistrationModel.id)
            .limit(1)
            # Several workers can run: each takes a different row, and none waits on another.
            .with_for_update(skip_locked=True)
        )
        if excluded_ids:
            statement = statement.where(PendingRegistrationModel.id.not_in(excluded_ids))
        model = await self._session.scalar(statement)
        if model is None:
            return None
        return PendingRegistration(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            attempts=model.attempts,
            request_id=model.request_id,
            ip_address=model.ip_address,
            user_agent=model.user_agent,
        )

    async def delete(self, registration_id: str) -> None:
        await self._session.execute(delete(PendingRegistrationModel).where(PendingRegistrationModel.id == registration_id))

    async def record_failure(self, registration_id: str, max_attempts: int) -> bool:
        model = await self._session.get(PendingRegistrationModel, registration_id)
        if model is None:
            return False
        model.attempts += 1
        if model.attempts >= max_attempts:
            await self._session.delete(model)
            return True
        return False

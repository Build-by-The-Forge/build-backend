import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.user import Session
from app.domain.identity.value_objects import (
    DeviceId,
    RefreshTokenHash,
    SessionId,
    UserId,
)
from app.infrastructure.identity.sqlalchemy_session_repository import (
    SQLAlchemySessionRepository,
)


@pytest.mark.asyncio
async def test_session_repository_can_save_and_retrieve(session: AsyncSession) -> None:
    repository = SQLAlchemySessionRepository(session)
    session_entity = Session(
        id=SessionId("session-1"),
        user_id=UserId("user-1"),
        device_id=DeviceId("device-1"),
        refresh_token_hash=RefreshTokenHash("refresh-hash"),
    )

    saved = await repository.save(session_entity)
    assert saved.id.value == "session-1"
    assert saved.refresh_token_hash is not None
    assert saved.refresh_token_hash.value == "refresh-hash"

    retrieved = await repository.get_by_id("session-1")
    assert retrieved is not None
    assert retrieved.id.value == "session-1"
    assert retrieved.user_id.value == "user-1"


@pytest.mark.asyncio
async def test_session_repository_can_find_by_refresh_token_and_list_active(
    session: AsyncSession,
) -> None:
    repository = SQLAlchemySessionRepository(session)
    session_entity = Session(
        id=SessionId("session-2"),
        user_id=UserId("user-2"),
        refresh_token_hash=RefreshTokenHash("refresh-hash-2"),
    )
    await repository.save(session_entity)

    found = await repository.get_by_refresh_token_hash("refresh-hash-2")
    assert found is not None
    assert found.id.value == "session-2"

    active = await repository.list_active_by_user_id("user-2")
    assert any(item.id.value == "session-2" for item in active)


@pytest.mark.asyncio
async def test_session_repository_can_revoke(session: AsyncSession) -> None:
    repository = SQLAlchemySessionRepository(session)
    session_entity = Session(
        id=SessionId("session-3"),
        user_id=UserId("user-3"),
        refresh_token_hash=RefreshTokenHash("refresh-hash-3"),
    )
    await repository.save(session_entity)

    await repository.revoke("session-3")
    revoked = await repository.get_by_id("session-3")
    assert revoked is not None
    assert revoked.revoked_at is not None

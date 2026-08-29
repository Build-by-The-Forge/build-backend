import pytest
from app.domain.identity.user import User
from app.domain.identity.value_objects import Email, PasswordHash, UserId
from app.infrastructure.identity.mappers import user_model_to_domain
from app.infrastructure.identity.models import UserModel
from app.infrastructure.identity.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_user_repository_can_save_and_retrieve_by_email(
    session: AsyncSession,
) -> None:
    repository = SQLAlchemyUserRepository(session)
    user = User(
        id=UserId("user-1"),
        email=Email("student@example.com"),
        password_hash=PasswordHash("hashed-password"),
    )

    saved_user = await repository.save(user)
    assert saved_user.email.value == "student@example.com"

    retrieved = await repository.get_by_email("student@example.com")
    assert retrieved is not None
    assert retrieved.id.value == "user-1"
    assert retrieved.email.value == user.email.value


@pytest.mark.asyncio
async def test_user_repository_exists_by_email(session: AsyncSession) -> None:
    repository = SQLAlchemyUserRepository(session)
    user = User(
        id=UserId("user-2"),
        email=Email("exists@example.com"),
        password_hash=PasswordHash("hashed-password"),
    )
    await repository.save(user)

    assert await repository.exists_by_email("exists@example.com") is True
    assert await repository.exists_by_email("missing@example.com") is False


@pytest.mark.asyncio
async def test_user_repository_can_update_password(session: AsyncSession) -> None:
    repository = SQLAlchemyUserRepository(session)
    user = User(
        id=UserId("user-3"),
        email=Email("update@example.com"),
        password_hash=PasswordHash("old-hash"),
    )
    await repository.save(user)

    user.password_hash = PasswordHash("new-hash")
    updated = await repository.save(user)

    assert updated.password_hash.value == "new-hash"

    result = await repository.get_by_email("update@example.com")
    assert result is not None
    assert result.password_hash.value == "new-hash"


@pytest.mark.asyncio
async def test_user_model_mapper_round_trip(session: AsyncSession) -> None:
    model = UserModel(
        id="user-4",
        email="roundtrip@example.com",
        password_hash="password-hash",
        is_active=True,
    )
    session.add(model)
    await session.flush()

    domain = user_model_to_domain(model)
    assert domain.id.value == "user-4"
    assert domain.email.value == "roundtrip@example.com"
    assert domain.password_hash.value == "password-hash"
    assert domain.is_active is True

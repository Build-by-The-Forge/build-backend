from datetime import datetime
from typing import Protocol

from app.domain.identity.user import User


class UserRepository(Protocol):
    async def save(self, user: User) -> User:
        raise NotImplementedError

    async def get_by_email(self, email: str) -> User | None:
        raise NotImplementedError

    async def get_by_id(self, user_id: str) -> User | None:
        raise NotImplementedError

    async def exists_by_email(self, email: str) -> bool:
        raise NotImplementedError

    async def save_password_reset_token(
        self, user_id: str, token_hash: str, expires_at: datetime | None = None
    ) -> None:
        raise NotImplementedError

    async def consume_password_reset_token(self, token_hash: str) -> str | None:
        raise NotImplementedError

    async def invalidate_password_reset_tokens(self, user_id: str) -> None:
        """Mark every outstanding reset token of the user as used."""
        raise NotImplementedError

    async def save_verification_token(
        self, user_id: str, token_hash: str, expires_at: datetime
    ) -> None:
        raise NotImplementedError

    async def consume_verification_token(self, token_hash: str) -> str | None:
        """Atomically mark a live verification token used; return its user id."""
        raise NotImplementedError

    async def invalidate_verification_tokens(self, user_id: str) -> None:
        raise NotImplementedError

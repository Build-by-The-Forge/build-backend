from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredRefreshToken:
    id: str
    session_id: str
    expires_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None


class RefreshTokenRepository(Protocol):
    async def add(self, session_id: str, token_hash: str, expires_at: datetime) -> None:
        raise NotImplementedError

    async def get_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        raise NotImplementedError

    async def consume(self, token_id: str) -> bool:
        """Atomically mark the token rotated if it is still current.

        Returns False if it was already rotated or revoked -- including by a
        concurrent request -- which callers must treat as token reuse.
        """
        raise NotImplementedError

    async def revoke_for_session(self, session_id: str) -> None:
        raise NotImplementedError

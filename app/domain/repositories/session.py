from typing import Protocol

from app.domain.identity.user import Session


class SessionRepository(Protocol):
    async def save(self, session: Session) -> Session:
        raise NotImplementedError

    async def claim_device(self, user_id: str, device_id: str) -> bool:
        """Record a new device for this user. False if it belongs to someone else."""
        raise NotImplementedError

    async def get_by_id(self, session_id: str) -> Session | None:
        raise NotImplementedError

    async def revoke_all_for_user(self, user_id: str, except_session_id: str | None = None) -> list[str]:
        raise NotImplementedError

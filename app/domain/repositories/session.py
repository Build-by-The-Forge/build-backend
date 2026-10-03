from typing import Protocol

from app.domain.identity.user import Session


class SessionRepository(Protocol):
    async def save(self, session: Session) -> Session:
        raise NotImplementedError

    async def get_by_id(self, session_id: str) -> Session | None:
        raise NotImplementedError

    async def revoke_all_for_user(self, user_id: str) -> list[str]:
        raise NotImplementedError

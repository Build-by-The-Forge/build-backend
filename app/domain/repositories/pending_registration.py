from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PendingRegistration:
    """An accepted registration, waiting for the worker. Its password is already hashed."""

    id: str
    email: str
    password_hash: str
    attempts: int
    request_id: str | None
    ip_address: str | None
    user_agent: str | None


class PendingRegistrationRepository(Protocol):
    async def add(
        self,
        email: str,
        password_hash: str,
        *,
        request_id: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        raise NotImplementedError

    async def claim_next(self, excluded_ids: set[str]) -> PendingRegistration | None:
        """The oldest not already claimed, locked until the transaction ends."""
        raise NotImplementedError

    async def delete(self, registration_id: str) -> None:
        raise NotImplementedError

    async def record_failure(self, registration_id: str, max_attempts: int) -> bool:
        """Count a failed attempt. True if that was the last, and the row is gone."""
        raise NotImplementedError

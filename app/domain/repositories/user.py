from typing import Protocol


class UserRepository(Protocol):
    async def save(self, user: object) -> object:
        raise NotImplementedError

    async def get_by_email(self, email: str) -> object | None:
        raise NotImplementedError

from typing import Protocol


class UserRepository(Protocol):
    async def save(self, user: object) -> object:
        raise NotImplementedError

    async def get_by_email(self, email: str) -> object | None:
        raise NotImplementedError

    async def get_by_id(self, user_id: str) -> object | None:
        raise NotImplementedError

    async def exists_by_email(self, email: str) -> bool:
        raise NotImplementedError

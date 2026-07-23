from typing import Protocol


class UserRepository(Protocol):
    async def save(self, user: object) -> object:
        raise NotImplementedError

from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    async def save(self, user: User) -> User:
        self._users[user.email.value] = user
        return user

    async def exists_by_email(self, email: str) -> bool:
        return email.lower() in self._users

    async def get_by_email(self, email: str) -> User | None:
        return self._users.get(email.lower())

    async def get_by_id(self, user_id: str) -> User | None:
        for user in self._users.values():
            if user.id.value == user_id:
                return user
        return None

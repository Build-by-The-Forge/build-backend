from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    async def save(self, user: User) -> User:
        self._users[user.email] = user
        return user

    async def exists_by_email(self, email: str) -> bool:
        return email in self._users

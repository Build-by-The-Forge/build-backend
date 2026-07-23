from app.core.exceptions import AppError
from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def register_user(self, email: str, password: str) -> User:
        if await self.repository.exists_by_email(email):
            raise AppError("User already exists", status_code=409)

        password_hash = self._hash_password(password)
        user = User(id="", email=email, password_hash=password_hash)
        return await self.repository.save(user)

    def _hash_password(self, password: str) -> str:
        return f"hashed:{password}"

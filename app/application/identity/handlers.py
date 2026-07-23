from app.application.identity.commands import AuthenticateUserCommand, RegisterUserCommand
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.token_service import TokenService
from app.core.exceptions import AppError
from app.domain.identity.user import Session, User
from app.domain.identity.value_objects import (
    DeviceId,
    Email,
    Password,
    PasswordHash,
    RefreshTokenHash,
    SessionId,
    UserId,
)
from app.domain.repositories.user import UserRepository
from app.events.event_bus import EventBus


class RegisterUserHandler:
    def __init__(self, repository: UserRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def handle(self, command: RegisterUserCommand) -> User:
        try:
            email = Email(command.email)
        except ValueError as exc:
            raise AppError("invalid email format", status_code=422) from exc

        if await self.repository.exists_by_email(email.value):
            raise AppError("User already exists", status_code=409)

        if len(command.password) < 12:
            raise AppError("Password must be at least 12 characters", status_code=422)

        password_hash = PasswordHash(self._hash_password(command.password))
        user = User(
            id=UserId(""),
            email=email,
            password_hash=password_hash,
        )
        saved_user = await self.repository.save(user)
        self.event_bus.publish("user.registered", payload={"user_id": saved_user.id.value, "email": saved_user.email.value})
        return saved_user

    def _hash_password(self, password: str) -> str:
        return f"hashed:{password}"


class AuthenticateUserHandler:
    def __init__(
        self,
        repository: UserRepository,
        event_bus: EventBus,
        password_hasher: PasswordHasher,
        token_service: TokenService,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.password_hasher = password_hasher
        self.token_service = token_service

    async def handle(self, command: AuthenticateUserCommand) -> Session:
        email = Email(command.email)
        user = await self.repository.get_by_email(email.value)
        if user is None:
            raise AppError("invalid credentials", status_code=401)

        password = Password(command.password)
        if not self.password_hasher.verify(password, user.password_hash):
            raise AppError("invalid credentials", status_code=401)

        session = Session(
            id=SessionId("session-generated"),
            user_id=user.id,
            device_id=DeviceId(command.device_id) if command.device_id else None,
            refresh_token_hash=RefreshTokenHash("refresh-token"),
            user_agent=command.user_agent,
        )
        self.event_bus.publish("session.started", payload={"user_id": user.id.value, "session_id": session.id.value})
        self.token_service.issue_access_token(user.id.value)
        self.token_service.issue_refresh_token(user.id.value)
        return session

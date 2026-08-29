from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.identity.commands import (
    AuthenticateUserCommand,
    ForgotPasswordCommand,
    GetCurrentUserCommand,
    LogoutSessionCommand,
    RefreshSessionCommand,
    RegisterUserCommand,
    ResetPasswordCommand,
)
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.token_service import TokenService
from app.core.exceptions import AppError
from app.domain.identity.user import Session, User
from app.domain.identity.value_objects import (
    DeviceId,
    Email,
    Password,
    RefreshTokenHash,
    SessionId,
    UserId,
)
from app.domain.repositories.session import SessionRepository
from app.domain.repositories.user import UserRepository
from app.events.base import DomainEvent


class RegisterUserHandler:
    def __init__(
        self, repository: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    async def handle(self, command: RegisterUserCommand) -> User:
        try:
            email = Email(command.email)
        except ValueError as exc:
            raise AppError("invalid email format", status_code=422) from exc

        if await self.repository.exists_by_email(email.value):
            raise AppError("User already exists", status_code=409)

        try:
            password = Password(command.password)
        except ValueError as exc:
            raise AppError(str(exc), status_code=422) from exc

        password_hash = self.password_hasher.hash(password)
        user = User(
            id=UserId(""),
            email=email,
            password_hash=password_hash,
        )
        saved_user = await self.repository.save(user)
        saved_user.record_event(
            DomainEvent(
                event_type="user.registered",
                payload={
                    "user_id": saved_user.id.value,
                    "email": saved_user.email.value,
                },
            )
        )
        return saved_user


class AuthenticateUserHandler:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        session_repository: SessionRepository | None = None,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.session_repository = session_repository

    async def handle(self, command: AuthenticateUserCommand) -> Session:
        email = Email(command.email)
        user = await self.repository.get_by_email(email.value)
        if user is None:
            raise AppError("invalid credentials", status_code=401)

        try:
            password = Password(command.password)
        except ValueError as exc:
            raise AppError(str(exc), status_code=422) from exc

        if not self.password_hasher.verify(password, user.password_hash):
            raise AppError("invalid credentials", status_code=401)

        refresh_token = self.token_service.issue_refresh_token(user.id.value)
        session = Session(
            id=SessionId(str(uuid4())),
            user_id=user.id,
            device_id=DeviceId(command.device_id) if command.device_id else None,
            refresh_token_hash=RefreshTokenHash(refresh_token),
            user_agent=command.user_agent,
        )
        if self.session_repository is not None:
            await self.session_repository.save(session)

        session.record_event(
            DomainEvent(
                event_type="session.started",
                payload={"user_id": user.id.value, "session_id": session.id.value},
            )
        )
        self.token_service.issue_access_token(user.id.value)
        return session


class RefreshSessionHandler:
    def __init__(
        self, session_repository: SessionRepository, token_service: TokenService
    ) -> None:
        self.session_repository = session_repository
        self.token_service = token_service

    async def handle(self, command: RefreshSessionCommand) -> Session:
        session = await self.session_repository.get_by_id(command.session_id)
        if session is None:
            raise AppError("session not found", status_code=404)

        if session.revoked_at is not None:
            raise AppError("session revoked", status_code=401)

        if session.refresh_token_hash is None:
            raise AppError("invalid refresh token", status_code=401)

        if command.refresh_token != session.refresh_token_hash.value:
            raise AppError("invalid refresh token", status_code=401)

        session.touch()
        session.record_event(
            DomainEvent(
                event_type="session.refreshed",
                payload={
                    "session_id": session.id.value,
                    "user_id": session.user_id.value,
                },
            )
        )
        self.token_service.issue_access_token(session.user_id.value)
        self.token_service.issue_refresh_token(session.user_id.value)
        return session


class LogoutSessionHandler:
    def __init__(self, session_repository: SessionRepository) -> None:
        self.session_repository = session_repository

    async def handle(self, command: LogoutSessionCommand) -> None:
        session = await self.session_repository.get_by_id(command.session_id)
        if session is None:
            raise AppError("session not found", status_code=404)

        session.revoke()
        await self.session_repository.save(session)


class ForgotPasswordHandler:
    def __init__(
        self, repository: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    async def handle(self, command: ForgotPasswordCommand) -> str:
        try:
            email = Email(command.email)
        except ValueError as exc:
            raise AppError("invalid email format", status_code=422) from exc

        user = await self.repository.get_by_email(email.value)
        if user is None:
            return ""

        raw_token = str(uuid4())
        token_hash = self.password_hasher.hash(Password(raw_token))
        await self.repository.save_password_reset_token(
            user.id.value,
            token_hash.value,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        return raw_token


class ResetPasswordHandler:
    def __init__(
        self, repository: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    async def handle(self, command: ResetPasswordCommand) -> None:
        if not command.token:
            raise AppError("invalid reset token", status_code=422)

        try:
            password = Password(command.password)
        except ValueError as exc:
            raise AppError(str(exc), status_code=422) from exc

        token_hash = self.password_hasher.hash(Password(command.token)).value
        user_id = await self.repository.consume_password_reset_token(token_hash)
        if user_id is None:
            raise AppError("invalid reset token", status_code=401)

        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise AppError("user not found", status_code=404)

        user.change_password(password, self.password_hasher)
        await self.repository.save(user)


class GetCurrentUserHandler:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetCurrentUserCommand) -> User:
        user = await self.repository.get_by_id(command.user_id)
        if user is None:
            raise AppError("user not found", status_code=404)
        return user

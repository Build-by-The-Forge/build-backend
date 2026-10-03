import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.identity.commands import (
    AuthenticateUserCommand,
    ForgotPasswordCommand,
    GetCurrentUserCommand,
    LogoutAllSessionsCommand,
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
    SessionId,
    UserId,
)
from app.domain.repositories.refresh_token import RefreshTokenRepository
from app.domain.repositories.session import SessionRepository
from app.domain.repositories.user import UserRepository
from app.events.base import DomainEvent


DEFAULT_SESSION_LIFETIME = timedelta(days=30)
DEFAULT_REFRESH_IDLE_LIFETIME = timedelta(days=14)


def hash_token(raw_token: str) -> str:
    # One-time tokens are looked up by their hash, so the hash must be
    # deterministic (unlike a salted password hash).
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def refresh_token_expiry(session: Session, idle: timedelta, now: datetime) -> datetime:
    """Idle expiry, never beyond the session's absolute expiry."""
    expiry = now + idle
    if session.expires_at is not None:
        expiry = min(expiry, _as_utc(session.expires_at))
    return expiry


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session: Session
    refresh_token: str


class RefreshTokenReuseError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__("refresh token reuse detected")
        self.session_id = session_id


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
        session_lifetime: timedelta = DEFAULT_SESSION_LIFETIME,
        refresh_token_repository: RefreshTokenRepository | None = None,
        refresh_idle_lifetime: timedelta = DEFAULT_REFRESH_IDLE_LIFETIME,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.session_repository = session_repository
        self.session_lifetime = session_lifetime
        self.refresh_token_repository = refresh_token_repository
        self.refresh_idle_lifetime = refresh_idle_lifetime

    async def handle(self, command: AuthenticateUserCommand) -> "IssuedSession":
        # Validate input before touching the account, so the outcome cannot
        # differ between existing and unknown emails.
        try:
            email = Email(command.email)
            password = Password(command.password)
        except ValueError as exc:
            raise AppError("invalid credentials", status_code=401) from exc

        user = await self.repository.get_by_email(email.value)
        if user is None:
            self.password_hasher.dummy_verify(password)
            raise AppError("invalid credentials", status_code=401)

        if not self.password_hasher.verify(password, user.password_hash):
            raise AppError("invalid credentials", status_code=401)

        # Checked only after the password verifies, so this reveals the
        # account state only to someone who already holds the credentials.
        if not user.can_authenticate:
            raise AppError("account is not active", status_code=403)

        if self.password_hasher.needs_rehash(user.password_hash):
            user.change_password(password, self.password_hasher)
            await self.repository.save(user)

        now = datetime.now(timezone.utc)
        session = Session(
            id=SessionId(str(uuid4())),
            user_id=user.id,
            device_id=DeviceId(command.device_id) if command.device_id else None,
            user_agent=command.user_agent,
            expires_at=now + self.session_lifetime,
        )
        if self.session_repository is not None:
            await self.session_repository.save(session)

        refresh_token = generate_refresh_token()
        if self.refresh_token_repository is not None:
            await self.refresh_token_repository.add(
                session.id.value,
                hash_token(refresh_token),
                refresh_token_expiry(session, self.refresh_idle_lifetime, now),
            )

        session.record_event(
            DomainEvent(
                event_type="session.started",
                payload={"user_id": user.id.value, "session_id": session.id.value},
            )
        )
        return IssuedSession(session=session, refresh_token=refresh_token)


class RefreshSessionHandler:
    """Rotate a refresh token. Presenting an already-rotated token is treated
    as theft: RefreshTokenReuseError is raised so the caller can revoke the
    whole session outside this (rolled-back) unit of work."""

    def __init__(
        self,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
        user_repository: UserRepository,
        refresh_idle_lifetime: timedelta = DEFAULT_REFRESH_IDLE_LIFETIME,
    ) -> None:
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository
        self.user_repository = user_repository
        self.refresh_idle_lifetime = refresh_idle_lifetime

    async def handle(self, command: RefreshSessionCommand) -> IssuedSession:
        invalid = AppError("invalid refresh token", status_code=401)
        if not command.refresh_token:
            raise invalid

        stored = await self.refresh_token_repository.get_by_hash(
            hash_token(command.refresh_token)
        )
        if stored is None or stored.revoked_at is not None:
            raise invalid
        if stored.rotated_at is not None:
            raise RefreshTokenReuseError(stored.session_id)

        now = datetime.now(timezone.utc)
        if stored.expires_at is not None and _as_utc(stored.expires_at) <= now:
            raise invalid

        session = await self.session_repository.get_by_id(stored.session_id)
        if session is None or not session.is_active_at(now):
            raise invalid
        user = await self.user_repository.get_by_id(session.user_id.value)
        if user is None or not user.can_authenticate:
            raise invalid

        # Atomic: if a concurrent request rotated it first, this is reuse.
        if not await self.refresh_token_repository.consume(stored.id):
            raise RefreshTokenReuseError(stored.session_id)

        refresh_token = generate_refresh_token()
        await self.refresh_token_repository.add(
            session.id.value,
            hash_token(refresh_token),
            refresh_token_expiry(session, self.refresh_idle_lifetime, now),
        )
        session.touch()
        await self.session_repository.save(session)

        session.record_event(
            DomainEvent(
                event_type="session.refreshed",
                payload={
                    "session_id": session.id.value,
                    "user_id": session.user_id.value,
                },
            )
        )
        return IssuedSession(session=session, refresh_token=refresh_token)


class RevokeSessionHandler:
    def __init__(
        self,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository

    async def handle(self, session_id: str) -> None:
        session = await self.session_repository.get_by_id(session_id)
        if session is not None and session.revoked_at is None:
            session.revoke()
            await self.session_repository.save(session)
        await self.refresh_token_repository.revoke_for_session(session_id)


class LogoutSessionHandler:
    def __init__(
        self,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository

    async def handle(self, command: LogoutSessionCommand) -> None:
        session = await self.session_repository.get_by_id(command.session_id)
        if session is None or session.user_id.value != command.user_id:
            raise AppError("session not found", status_code=404)

        await RevokeSessionHandler(
            self.session_repository, self.refresh_token_repository
        ).handle(command.session_id)


class LogoutAllSessionsHandler:
    def __init__(
        self,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository

    async def handle(self, command: LogoutAllSessionsCommand) -> int:
        session_ids = await self.session_repository.revoke_all_for_user(command.user_id)
        for session_id in session_ids:
            await self.refresh_token_repository.revoke_for_session(session_id)
        return len(session_ids)


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
        await self.repository.save_password_reset_token(
            user.id.value,
            hash_token(raw_token),
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

        user_id = await self.repository.consume_password_reset_token(
            hash_token(command.token)
        )
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

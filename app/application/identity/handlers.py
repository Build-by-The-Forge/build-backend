import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.identity.commands import (
    AuthenticateUserCommand,
    ChangePasswordCommand,
    ForgotPasswordCommand,
    GetCurrentUserCommand,
    LogoutAllSessionsCommand,
    LogoutSessionCommand,
    RefreshSessionCommand,
    RegisterUserCommand,
    RequestEmailVerificationCommand,
    ResetPasswordCommand,
    VerifyEmailCommand,
)
from app.application.identity.ports.email_sender import EmailMessage
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.token_service import TokenService
from app.core.exceptions import AppError
from app.domain.identity.user import Session, User
from app.domain.identity.value_objects import (
    AccountStatus,
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


async def revoke_user_sessions(
    session_repository: SessionRepository,
    refresh_token_repository: RefreshTokenRepository,
    user_id: str,
    except_session_id: str | None = None,
) -> int:
    """Revoke every live session of the user together with its refresh tokens."""
    session_ids = await session_repository.revoke_all_for_user(
        user_id, except_session_id=except_session_id
    )
    for session_id in session_ids:
        await refresh_token_repository.revoke_for_session(session_id)
    return len(session_ids)


class LogoutAllSessionsHandler:
    def __init__(
        self,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository

    async def handle(self, command: LogoutAllSessionsCommand) -> int:
        return await revoke_user_sessions(
            self.session_repository, self.refresh_token_repository, command.user_id
        )


DEFAULT_PASSWORD_RESET_LIFETIME = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class PasswordResetRequest:
    """A reset token to deliver out of band; never returned to the caller."""

    email: str
    raw_token: str
    expires_in: timedelta


def password_reset_email(request: PasswordResetRequest) -> EmailMessage:
    minutes = int(request.expires_in.total_seconds() // 60)
    return EmailMessage(
        to=request.email,
        subject="Reset your BUILD password",
        body=(
            "Use this code to reset your BUILD password:\n\n"
            f"{request.raw_token}\n\n"
            f"It expires in {minutes} minutes and can be used once. "
            "If you did not ask for this, you can ignore this email."
        ),
    )


class ForgotPasswordHandler:
    def __init__(
        self,
        repository: UserRepository,
        reset_lifetime: timedelta = DEFAULT_PASSWORD_RESET_LIFETIME,
    ) -> None:
        self.repository = repository
        self.reset_lifetime = reset_lifetime

    async def handle(self, command: ForgotPasswordCommand) -> PasswordResetRequest | None:
        try:
            email = Email(command.email)
        except ValueError as exc:
            raise AppError("invalid email format", status_code=422) from exc

        user = await self.repository.get_by_email(email.value)
        # Unknown and blocked accounts get no token; the caller's response
        # must not reveal which case applied.
        if user is None or not user.can_authenticate:
            return None

        await self.repository.invalidate_password_reset_tokens(user.id.value)
        raw_token = secrets.token_urlsafe(32)
        await self.repository.save_password_reset_token(
            user.id.value,
            hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + self.reset_lifetime,
        )
        return PasswordResetRequest(
            email=user.email.value, raw_token=raw_token, expires_in=self.reset_lifetime
        )


class ResetPasswordHandler:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository

    async def handle(self, command: ResetPasswordCommand) -> str:
        """Reset the password; return the account's email."""
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
        # A blocked account must not regain access through reset; answer as
        # for a bad code so the response says nothing about the account.
        if user is None or not user.can_authenticate:
            raise AppError("invalid reset token", status_code=401)

        user.change_password(password, self.password_hasher)
        await self.repository.save(user)
        await self.repository.invalidate_password_reset_tokens(user_id)
        # Whoever prompted the reset may hold a live session; end them all.
        await revoke_user_sessions(
            self.session_repository, self.refresh_token_repository, user_id
        )
        return user.email.value


DEFAULT_EMAIL_VERIFICATION_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class EmailVerificationRequest:
    """A verification code to deliver out of band; never returned to the caller."""

    email: str
    raw_token: str
    expires_in: timedelta


def email_verification_email(request: EmailVerificationRequest) -> EmailMessage:
    hours = int(request.expires_in.total_seconds() // 3600)
    return EmailMessage(
        to=request.email,
        subject="Verify your BUILD email address",
        body=(
            "Use this code to verify your email address for BUILD:\n\n"
            f"{request.raw_token}\n\n"
            f"It expires in {hours} hours and can be used once."
        ),
    )


async def issue_email_verification(
    repository: UserRepository, user: User, lifetime: timedelta
) -> EmailVerificationRequest:
    """Replace any outstanding verification code of the user with a new one."""
    await repository.invalidate_verification_tokens(user.id.value)
    raw_token = secrets.token_urlsafe(32)
    await repository.save_verification_token(
        user.id.value,
        hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + lifetime,
    )
    return EmailVerificationRequest(
        email=user.email.value, raw_token=raw_token, expires_in=lifetime
    )


class RequestEmailVerificationHandler:
    def __init__(
        self,
        repository: UserRepository,
        lifetime: timedelta = DEFAULT_EMAIL_VERIFICATION_LIFETIME,
    ) -> None:
        self.repository = repository
        self.lifetime = lifetime

    async def handle(
        self, command: RequestEmailVerificationCommand
    ) -> EmailVerificationRequest | None:
        try:
            email = Email(command.email)
        except ValueError as exc:
            raise AppError("invalid email format", status_code=422) from exc

        user = await self.repository.get_by_email(email.value)
        # Only pending accounts that may sign in get a code; the caller's
        # response must not reveal which case applied.
        if (
            user is None
            or not user.can_authenticate
            or user.status is not AccountStatus.PENDING_VERIFICATION
        ):
            return None
        return await issue_email_verification(self.repository, user, self.lifetime)


class VerifyEmailHandler:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def handle(self, command: VerifyEmailCommand) -> User:
        if not command.token:
            raise AppError("invalid verification token", status_code=422)

        user_id = await self.repository.consume_verification_token(
            hash_token(command.token)
        )
        if user_id is None:
            raise AppError("invalid verification token", status_code=401)

        user = await self.repository.get_by_id(user_id)
        # Verification only ever activates a pending account; it must not
        # bring back one that was locked, disabled or deleted.
        if (
            user is None
            or not user.can_authenticate
            or user.status is not AccountStatus.PENDING_VERIFICATION
        ):
            raise AppError("invalid verification token", status_code=401)

        user.verify_email()
        await self.repository.save(user)
        await self.repository.invalidate_verification_tokens(user_id)
        return user


class ChangePasswordHandler:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        session_repository: SessionRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.session_repository = session_repository
        self.refresh_token_repository = refresh_token_repository

    async def handle(self, command: ChangePasswordCommand) -> int:
        """Change the caller's password; return how many other sessions ended."""
        try:
            new_password = Password(command.new_password)
        except ValueError as exc:
            raise AppError(str(exc), status_code=422) from exc

        user = await self.repository.get_by_id(command.user_id)
        if user is None or not user.can_authenticate:
            raise AppError("invalid credentials", status_code=401)

        # Not 401: the caller's token is fine, and a 401 would push clients
        # into a pointless refresh. Input that cannot be a valid password
        # cannot be the current one.
        try:
            current_password = Password(command.current_password)
        except ValueError:
            current_password = None
        if current_password is None or not self.password_hasher.verify(
            current_password, user.password_hash
        ):
            raise AppError("current password is incorrect", status_code=400)
        if command.new_password == command.current_password:
            raise AppError(
                "new password must differ from the current password", status_code=422
            )

        user.change_password(new_password, self.password_hasher)
        await self.repository.save(user)
        await self.repository.invalidate_password_reset_tokens(user.id.value)
        if not command.revoke_other_sessions:
            return 0
        return await revoke_user_sessions(
            self.session_repository,
            self.refresh_token_repository,
            user.id.value,
            except_session_id=command.session_id,
        )


class GetCurrentUserHandler:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetCurrentUserCommand) -> User:
        user = await self.repository.get_by_id(command.user_id)
        if user is None:
            raise AppError("user not found", status_code=404)
        return user

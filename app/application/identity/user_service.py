import asyncio
from datetime import timedelta

import structlog

from app.application.common.uow import IdentityUnitOfWorkFactory
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
from app.application.identity.handlers import (
    AuthenticateUserHandler,
    AuthenticationFailed,
    ChangePasswordHandler,
    CurrentPasswordIncorrect,
    ForgotPasswordHandler,
    GetCurrentUserHandler,
    IssuedSession,
    LogoutAllSessionsHandler,
    LogoutSessionHandler,
    RefreshSessionHandler,
    RefreshTokenReuseError,
    RegisterUserHandler,
    RegistrationRequest,
    RequestEmailVerificationHandler,
    ResetPasswordHandler,
    RevokeSessionHandler,
    VerifyEmailHandler,
    email_verification_email,
    issue_email_verification,
    password_reset_email,
    prepare_registration,
)
from app.application.identity.ports.email_sender import EmailSender
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.security_events import (
    LoginFailureReason,
    SecurityEvent,
    SecurityEventRecorder,
)
from app.application.identity.ports.token_service import TokenService
from app.core.config import settings
from app.core.exceptions import ClientError
from app.core.request_context import RequestMeta, current_request
from app.domain.identity.user import User
from app.domain.identity.value_objects import Email, PasswordHash
from app.domain.repositories.user import UserRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus

logger = structlog.get_logger(__name__)
# Enough to outlast a brief outage: the row holds a password hash, so it doesn't wait forever.
MAX_REGISTRATION_ATTEMPTS = 5


class UserService:
    def __init__(
        self,
        repository: UserRepository | None,
        event_bus: EventBus,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        uow_factory: IdentityUnitOfWorkFactory | None = None,
        *,
        email_sender: EmailSender,
        security_events: SecurityEventRecorder,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.uow_factory = uow_factory
        self.email_sender = email_sender
        self.security_events = security_events

    async def accept_registration(self, email: str, password: str) -> None:
        """Refuses what breaks a rule, and records everything else. Nothing here looks for
        the account, so every accepted request does the same work and gets the same answer."""
        request = prepare_registration(RegisterUserCommand(email=email, password=password), self.password_hasher)
        meta = current_request.get()
        async with self.uow_factory() as uow:
            await uow.pending_registrations.add(
                request.email.value,
                request.password_hash.value,
                request_id=meta.request_id,
                ip_address=meta.ip,
                user_agent=meta.user_agent,
            )

    async def process_pending_registrations(self, stop: asyncio.Event | None = None) -> None:
        """One pass over what's waiting. A row that fails stays for the next pass, up to its
        limit. Only the worker runs this, away from the requests it could otherwise slow."""
        excluded_ids: set[str] = set()
        while not (stop and stop.is_set()):
            claimed: list[str] = []
            try:
                if not await self._process_one_registration(excluded_ids, claimed):
                    return
            except Exception as exc:
                if not claimed:
                    raise
                try:
                    await self._record_registration_failure(claimed[-1], exc)
                except Exception:
                    # It's retried next pass regardless. This pass still has other rows.
                    logger.exception("registration_failure_not_recorded", registration_id=claimed[-1])
            excluded_ids.update(claimed)

    async def _process_one_registration(self, excluded_ids: set[str], claimed: list[str]) -> bool:
        async with self.uow_factory() as uow:
            pending = await uow.pending_registrations.claim_next(excluded_ids)
            if pending is None:
                return False
            claimed.append(pending.id)
            request = RegistrationRequest(email=Email(pending.email), password_hash=PasswordHash(pending.password_hash))
            user = await RegisterUserHandler(repository=uow.users).handle(request)
            verification = None
            if user is not None:
                verification = await issue_email_verification(uow.users, user, self._verification_lifetime())
            await uow.pending_registrations.delete(pending.id)

        # Committed: the row and its password hash are gone whatever happens next, and an
        # undelivered email can be asked for again.
        if user is None:
            return True
        token = current_request.set(RequestMeta(pending.request_id, pending.ip_address, pending.user_agent))
        try:
            try:
                await self.email_sender.send(email_verification_email(verification))
            except Exception:
                logger.exception("registration_email_failed", user_id=user.id.value)
            await self.security_events.record(SecurityEvent.ACCOUNT_REGISTERED, user_id=user.id.value)
            self._publish_events(user.pull_events())
        finally:
            current_request.reset(token)
        return True

    async def _record_registration_failure(self, registration_id: str, exc: Exception) -> None:
        async with self.uow_factory() as uow:
            dropped = await uow.pending_registrations.record_failure(registration_id, MAX_REGISTRATION_ATTEMPTS)
        logger.error(
            "registration_dropped" if dropped else "registration_failed",
            registration_id=registration_id,
            error_type=type(exc).__name__,
        )

    async def authenticate_user(
        self,
        email: str,
        password: str,
        device_id: str | None = None,
        user_agent: str | None = None,
    ) -> IssuedSession:
        command = AuthenticateUserCommand(
            email=email,
            password=password,
            device_id=device_id,
            user_agent=user_agent,
        )
        try:
            issued = await self._authenticate(command)
        except AuthenticationFailed as failure:
            await self.security_events.record_login(
                user_id=failure.user_id,
                successful=False,
                reason=LoginFailureReason(failure.reason),
            )
            raise
        await self.security_events.record_login(user_id=issued.session.user_id.value, successful=True)
        self._publish_events(issued.session.pull_events())
        return issued

    async def _authenticate(self, command: AuthenticateUserCommand) -> IssuedSession:
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = AuthenticateUserHandler(
                    repository=uow.users,
                    session_repository=uow.sessions,
                    refresh_token_repository=uow.refresh_tokens,
                    password_hasher=self.password_hasher,
                    token_service=self.token_service,
                    session_lifetime=timedelta(seconds=settings.auth_session_absolute_ttl_seconds),
                    refresh_idle_lifetime=timedelta(seconds=settings.auth_refresh_idle_ttl_seconds),
                )
                return await handler.handle(command)

        return await AuthenticateUserHandler(
            repository=self.repository,
            password_hasher=self.password_hasher,
            token_service=self.token_service,
        ).handle(command)

    async def refresh_session(self, refresh_token: str) -> IssuedSession:
        uow_factory = self._require_uow()
        try:
            async with uow_factory() as uow:
                issued = await RefreshSessionHandler(
                    session_repository=uow.sessions,
                    refresh_token_repository=uow.refresh_tokens,
                    user_repository=uow.users,
                    refresh_idle_lifetime=timedelta(seconds=settings.auth_refresh_idle_ttl_seconds),
                ).handle(RefreshSessionCommand(refresh_token=refresh_token))
        except RefreshTokenReuseError as reuse:
            # A rotated token was presented again: treat as theft and revoke
            # the whole session. Done in its own unit of work because the one
            # above rolled back.
            async with uow_factory() as uow:
                session = await RevokeSessionHandler(uow.sessions, uow.refresh_tokens).handle(reuse.session_id)
            await self.security_events.record(
                SecurityEvent.REFRESH_TOKEN_REUSE,
                user_id=session.user_id.value if session else None,
                metadata={"session_id": reuse.session_id},
            )
            raise ClientError("invalid refresh token", status_code=401, code="AUTH_REFRESH_INVALID") from None

        self._publish_events(issued.session.pull_events())
        return issued

    async def logout_session(self, session_id: str, user_id: str) -> None:
        async with self._require_uow()() as uow:
            await LogoutSessionHandler(uow.sessions, uow.refresh_tokens).handle(
                LogoutSessionCommand(session_id=session_id, user_id=user_id)
            )
        await self.security_events.record(SecurityEvent.LOGOUT, user_id=user_id, metadata={"session_id": session_id})

    async def logout_all_sessions(self, user_id: str) -> int:
        async with self._require_uow()() as uow:
            revoked = await LogoutAllSessionsHandler(uow.sessions, uow.refresh_tokens).handle(
                LogoutAllSessionsCommand(user_id=user_id)
            )
        await self.security_events.record(
            SecurityEvent.LOGOUT_ALL,
            user_id=user_id,
            metadata={"revoked_sessions": revoked},
        )
        return revoked

    def _require_uow(self) -> IdentityUnitOfWorkFactory:
        if self.uow_factory is None:
            raise RuntimeError("session operations require a unit of work")
        return self.uow_factory

    async def forgot_password(self, email: str) -> None:
        lifetime = timedelta(seconds=settings.auth_password_reset_ttl_seconds)
        command = ForgotPasswordCommand(email=email)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                request = await ForgotPasswordHandler(uow.users, lifetime).handle(command)
        else:
            request = await ForgotPasswordHandler(self.repository, lifetime).handle(command)

        # Sent only after the token is committed, so a delivered code always works.
        if request is not None:
            await self.email_sender.send(password_reset_email(request))
            await self.security_events.record(SecurityEvent.PASSWORD_RESET_REQUESTED, user_id=request.user_id)

    async def reset_password(self, token: str, password: str) -> str:
        command = ResetPasswordCommand(token=token, password=password)
        async with self._require_uow()() as uow:
            user = await ResetPasswordHandler(uow.users, self.password_hasher, uow.sessions, uow.refresh_tokens).handle(command)
        await self.security_events.record(SecurityEvent.PASSWORD_RESET_COMPLETED, user_id=user.id.value)
        return user.email.value

    async def change_password(
        self,
        user_id: str,
        session_id: str,
        current_password: str,
        new_password: str,
        revoke_other_sessions: bool = True,
    ) -> int:
        command = ChangePasswordCommand(
            user_id=user_id,
            session_id=session_id,
            current_password=current_password,
            new_password=new_password,
            revoke_other_sessions=revoke_other_sessions,
        )
        try:
            async with self._require_uow()() as uow:
                revoked = await ChangePasswordHandler(uow.users, self.password_hasher, uow.sessions, uow.refresh_tokens).handle(
                    command
                )
        except CurrentPasswordIncorrect:
            # With a valid session, a wrong current password can mean a
            # stolen token being used to take the account over.
            await self.security_events.record(
                SecurityEvent.PASSWORD_CHANGE_FAILED,
                user_id=user_id,
                metadata={"session_id": session_id},
            )
            raise
        await self.security_events.record(
            SecurityEvent.PASSWORD_CHANGED,
            user_id=user_id,
            metadata={"session_id": session_id, "revoked_sessions": revoked},
        )
        return revoked

    async def request_email_verification(self, email: str) -> None:
        async with self._require_uow()() as uow:
            verification = await RequestEmailVerificationHandler(uow.users, self._verification_lifetime()).handle(
                RequestEmailVerificationCommand(email=email)
            )
        if verification is not None:
            await self.email_sender.send(email_verification_email(verification))

    async def verify_email(self, token: str) -> User:
        async with self._require_uow()() as uow:
            user = await VerifyEmailHandler(uow.users).handle(VerifyEmailCommand(token=token))
        await self.security_events.record(SecurityEvent.EMAIL_VERIFIED, user_id=user.id.value)
        return user

    @staticmethod
    def _verification_lifetime() -> timedelta:
        return timedelta(seconds=settings.auth_email_verification_ttl_seconds)

    async def get_current_user(self, user_id: str) -> User:
        command = GetCurrentUserCommand(user_id=user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = GetCurrentUserHandler(repository=uow.users)
                return await handler.handle(command)

        handler = GetCurrentUserHandler(repository=self.repository)
        return await handler.handle(command)

    def _publish_events(self, events: list[DomainEvent]) -> None:
        self.event_bus.publish_all(events)

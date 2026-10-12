from datetime import timedelta

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
    RequestEmailVerificationHandler,
    ResetPasswordHandler,
    RevokeSessionHandler,
    VerifyEmailHandler,
    email_verification_email,
    issue_email_verification,
    password_reset_email,
)
from app.application.identity.ports.email_sender import EmailSender
from app.application.identity.ports.security_events import (
    LoginFailureReason,
    SecurityEvent,
    SecurityEventRecorder,
)
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.token_service import TokenService
from app.core.config import settings
from app.core.exceptions import AppError
from app.domain.identity.user import User
from app.domain.repositories.user import UserRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


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

    async def register_user(self, email: str, password: str) -> User:
        command = RegisterUserCommand(email=email, password=password)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = RegisterUserHandler(repository=uow.users, password_hasher=self.password_hasher)
                user = await handler.handle(command)
                verification = await issue_email_verification(uow.users, user, self._verification_lifetime())
            # Sent only after the account and code are committed.
            await self.email_sender.send(email_verification_email(verification))
            await self.security_events.record(SecurityEvent.ACCOUNT_REGISTERED, user_id=user.id.value)
            self._publish_events(user.pull_events())
            return user

        handler = RegisterUserHandler(repository=self.repository, password_hasher=self.password_hasher)
        user = await handler.handle(command)
        self._publish_events(user.pull_events())
        return user

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
            raise AppError("invalid refresh token", status_code=401) from None

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

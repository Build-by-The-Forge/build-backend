from datetime import timedelta

from app.application.common.uow import IdentityUnitOfWorkFactory
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
from app.application.identity.handlers import (
    AuthenticateUserHandler,
    ForgotPasswordHandler,
    GetCurrentUserHandler,
    IssuedSession,
    LogoutAllSessionsHandler,
    LogoutSessionHandler,
    RefreshSessionHandler,
    RefreshTokenReuseError,
    RegisterUserHandler,
    ResetPasswordHandler,
    RevokeSessionHandler,
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
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.uow_factory = uow_factory

    async def register_user(self, email: str, password: str) -> User:
        command = RegisterUserCommand(email=email, password=password)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = RegisterUserHandler(
                    repository=uow.users, password_hasher=self.password_hasher
                )
                user = await handler.handle(command)
            self._publish_events(user.pull_events())
            return user

        handler = RegisterUserHandler(
            repository=self.repository, password_hasher=self.password_hasher
        )
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
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = AuthenticateUserHandler(
                    repository=uow.users,
                    session_repository=uow.sessions,
                    refresh_token_repository=uow.refresh_tokens,
                    password_hasher=self.password_hasher,
                    token_service=self.token_service,
                    session_lifetime=timedelta(
                        seconds=settings.auth_session_absolute_ttl_seconds
                    ),
                    refresh_idle_lifetime=timedelta(
                        seconds=settings.auth_refresh_idle_ttl_seconds
                    ),
                )
                issued = await handler.handle(command)
            self._publish_events(issued.session.pull_events())
            return issued

        handler = AuthenticateUserHandler(
            repository=self.repository,
            password_hasher=self.password_hasher,
            token_service=self.token_service,
        )
        issued = await handler.handle(command)
        self._publish_events(issued.session.pull_events())
        return issued

    async def refresh_session(self, refresh_token: str) -> IssuedSession:
        uow_factory = self._require_uow()
        try:
            async with uow_factory() as uow:
                issued = await RefreshSessionHandler(
                    session_repository=uow.sessions,
                    refresh_token_repository=uow.refresh_tokens,
                    user_repository=uow.users,
                    refresh_idle_lifetime=timedelta(
                        seconds=settings.auth_refresh_idle_ttl_seconds
                    ),
                ).handle(RefreshSessionCommand(refresh_token=refresh_token))
        except RefreshTokenReuseError as reuse:
            # A rotated token was presented again: treat as theft and revoke
            # the whole session. Done in its own unit of work because the one
            # above rolled back.
            async with uow_factory() as uow:
                await RevokeSessionHandler(uow.sessions, uow.refresh_tokens).handle(
                    reuse.session_id
                )
            raise AppError("invalid refresh token", status_code=401) from None

        self._publish_events(issued.session.pull_events())
        return issued

    async def logout_session(self, session_id: str, user_id: str) -> None:
        async with self._require_uow()() as uow:
            await LogoutSessionHandler(uow.sessions, uow.refresh_tokens).handle(
                LogoutSessionCommand(session_id=session_id, user_id=user_id)
            )

    async def logout_all_sessions(self, user_id: str) -> int:
        async with self._require_uow()() as uow:
            return await LogoutAllSessionsHandler(
                uow.sessions, uow.refresh_tokens
            ).handle(LogoutAllSessionsCommand(user_id=user_id))

    def _require_uow(self) -> IdentityUnitOfWorkFactory:
        if self.uow_factory is None:
            raise RuntimeError("session operations require a unit of work")
        return self.uow_factory

    async def forgot_password(self, email: str) -> str:
        command = ForgotPasswordCommand(email=email)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ForgotPasswordHandler(
                    repository=uow.users, password_hasher=self.password_hasher
                )
                return await handler.handle(command)

        handler = ForgotPasswordHandler(
            repository=self.repository, password_hasher=self.password_hasher
        )
        return await handler.handle(command)

    async def reset_password(self, token: str, password: str) -> None:
        command = ResetPasswordCommand(token=token, password=password)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ResetPasswordHandler(
                    repository=uow.users, password_hasher=self.password_hasher
                )
                await handler.handle(command)
            return

        handler = ResetPasswordHandler(
            repository=self.repository, password_hasher=self.password_hasher
        )
        await handler.handle(command)

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

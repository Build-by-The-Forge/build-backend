from app.application.common.uow import IdentityUnitOfWorkFactory
from app.application.identity.commands import (
    AuthenticateUserCommand,
    ForgotPasswordCommand,
    GetCurrentUserCommand,
    LogoutSessionCommand,
    RefreshSessionCommand,
    RegisterUserCommand,
    ResetPasswordCommand,
)
from app.application.identity.handlers import (
    AuthenticateUserHandler,
    ForgotPasswordHandler,
    GetCurrentUserHandler,
    LogoutSessionHandler,
    RefreshSessionHandler,
    RegisterUserHandler,
    ResetPasswordHandler,
)
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.token_service import TokenService
from app.domain.identity.user import Session, User
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
    ) -> Session:
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
                    password_hasher=self.password_hasher,
                    token_service=self.token_service,
                )
                session = await handler.handle(command)
            self._publish_events(session.pull_events())
            return session

        handler = AuthenticateUserHandler(
            repository=self.repository,
            password_hasher=self.password_hasher,
            token_service=self.token_service,
        )
        session = await handler.handle(command)
        self._publish_events(session.pull_events())
        return session

    async def refresh_session(self, session_id: str, refresh_token: str) -> Session:
        command = RefreshSessionCommand(
            session_id=session_id, refresh_token=refresh_token
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = RefreshSessionHandler(
                    session_repository=uow.sessions, token_service=self.token_service
                )
                session = await handler.handle(command)
            self._publish_events(session.pull_events())
            return session

        handler = RefreshSessionHandler(
            session_repository=self.repository.sessions,
            token_service=self.token_service,
        )
        session = await handler.handle(command)
        self._publish_events(session.pull_events())
        return session

    async def logout_session(self, session_id: str) -> None:
        command = LogoutSessionCommand(session_id=session_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = LogoutSessionHandler(session_repository=uow.sessions)
                await handler.handle(command)
            return

        handler = LogoutSessionHandler(session_repository=self.repository.sessions)
        await handler.handle(command)

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

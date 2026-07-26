from collections.abc import AsyncIterator, Callable

from app.application.identity.commands import AuthenticateUserCommand, RegisterUserCommand
from app.application.identity.handlers import AuthenticateUserHandler, RegisterUserHandler
from app.application.identity.ports.password_hasher import PasswordHasher
from app.application.identity.ports.token_service import TokenService
from app.domain.identity.user import Session, User
from app.domain.repositories.user import UserRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


AsyncUnitOfWorkFactory = Callable[[], AsyncIterator[object]]


class UserService:
    def __init__(
        self,
        repository: UserRepository | None,
        event_bus: EventBus,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        uow_factory: AsyncUnitOfWorkFactory | None = None,
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
                handler = RegisterUserHandler(repository=uow.users, password_hasher=self.password_hasher)
                user = await handler.handle(command)
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

    def _publish_events(self, events: list[DomainEvent]) -> None:
        self.event_bus.publish_all(events)

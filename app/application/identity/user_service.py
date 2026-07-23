from app.application.identity.commands import AuthenticateUserCommand, RegisterUserCommand
from app.application.identity.handlers import AuthenticateUserHandler, RegisterUserHandler
from app.domain.identity.user import Session, User
from app.domain.repositories.user import UserRepository
from app.events.event_bus import EventBus


class UserService:
    def __init__(self, repository: UserRepository, event_bus: EventBus) -> None:
        self.register_handler = RegisterUserHandler(repository=repository, event_bus=event_bus)
        self.authenticate_handler = AuthenticateUserHandler(repository=repository, event_bus=event_bus)

    async def register_user(self, email: str, password: str) -> User:
        command = RegisterUserCommand(email=email, password=password)
        return await self.register_handler.handle(command)

    async def authenticate_user(self, email: str, password: str, device_id: str | None = None, user_agent: str | None = None) -> Session:
        command = AuthenticateUserCommand(email=email, password=password, device_id=device_id, user_agent=user_agent)
        return await self.authenticate_handler.handle(command)

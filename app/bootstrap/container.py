from app.application.identity.user_service import UserService
from app.events.event_bus import EventBus
from app.infrastructure.identity.memory_user_repository import InMemoryUserRepository
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService


class Container:
    def __init__(self) -> None:
        self._services: dict[type[object], object] = {}

    def register(self, service_type: type[object], implementation: object) -> None:
        self._services[service_type] = implementation

    def get(self, service_type: type[object]) -> object:
        if service_type not in self._services:
            raise KeyError(f"Service {service_type.__name__} is not registered")
        return self._services[service_type]


def build_container() -> Container:
    container = Container()
    event_bus = EventBus()
    repository = InMemoryUserRepository()
    password_hasher = Argon2PasswordHasher()
    token_service = JWTTokenService()

    container.register(EventBus, event_bus)
    container.register(InMemoryUserRepository, repository)
    container.register(Argon2PasswordHasher, password_hasher)
    container.register(JWTTokenService, token_service)
    container.register(
        UserService,
        UserService(
            repository=repository,
            event_bus=event_bus,
            password_hasher=password_hasher,
            token_service=token_service,
        ),
    )
    return container

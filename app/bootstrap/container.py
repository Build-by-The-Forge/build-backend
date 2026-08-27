from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.application.assessment.question_service import QuestionService
from app.application.catalogue.course_service import CourseService
from app.application.identity.user_service import UserService
from app.db.session import SessionLocal
from app.events.event_bus import EventBus
from app.infrastructure.assessment.unit_of_work import (
    AssessmentUnitOfWork,
    assessment_unit_of_work,
)
from app.infrastructure.catalogue.unit_of_work import (
    CourseUnitOfWork,
    catalogue_unit_of_work,
)
from app.infrastructure.identity.unit_of_work import (
    IdentityUnitOfWork,
    identity_unit_of_work,
)
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
    password_hasher = Argon2PasswordHasher()
    token_service = JWTTokenService()

    container.register(EventBus, event_bus)
    container.register(Argon2PasswordHasher, password_hasher)
    container.register(JWTTokenService, token_service)
    container.register(IdentityUnitOfWork, sqlalchemy_identity_uow)
    container.register(
        UserService,
        UserService(
            repository=None,
            event_bus=event_bus,
            password_hasher=password_hasher,
            token_service=token_service,
            uow_factory=sqlalchemy_identity_uow,
        ),
    )
    container.register(CourseUnitOfWork, sqlalchemy_catalogue_uow)
    container.register(
        CourseService,
        CourseService(
            repository=None,
            uow_factory=sqlalchemy_catalogue_uow,
        ),
    )
    container.register(AssessmentUnitOfWork, sqlalchemy_assessment_uow)
    container.register(
        QuestionService,
        QuestionService(
            repository=None,
            uow_factory=sqlalchemy_assessment_uow,
        ),
    )
    return container


@asynccontextmanager
async def sqlalchemy_identity_uow() -> AsyncIterator[IdentityUnitOfWork]:
    async with SessionLocal() as session:
        async with identity_unit_of_work(session) as uow:
            yield uow


@asynccontextmanager
async def sqlalchemy_catalogue_uow() -> AsyncIterator[CourseUnitOfWork]:
    async with SessionLocal() as session:
        async with catalogue_unit_of_work(session) as uow:
            yield uow


@asynccontextmanager
async def sqlalchemy_assessment_uow() -> AsyncIterator[AssessmentUnitOfWork]:
    async with SessionLocal() as session:
        async with assessment_unit_of_work(session) as uow:
            yield uow


def build_sqlalchemy_container() -> Container:
    container = Container()
    event_bus = EventBus()
    password_hasher = Argon2PasswordHasher()
    token_service = JWTTokenService()

    container.register(EventBus, event_bus)
    container.register(Argon2PasswordHasher, password_hasher)
    container.register(JWTTokenService, token_service)
    container.register(IdentityUnitOfWork, sqlalchemy_identity_uow)
    container.register(
        UserService,
        UserService(
            event_bus=event_bus,
            password_hasher=password_hasher,
            token_service=token_service,
            uow_factory=sqlalchemy_identity_uow,
        ),
    )
    return container

import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypeVar, cast

from app.application.assessment.assessment_service import AssessmentService
from app.application.assessment.attempt_answer_service import AttemptAnswerService
from app.application.assessment.attempt_service import AttemptService
from app.application.assessment.question_service import QuestionService
from app.application.catalogue.course_service import CourseService
from app.application.content.asset_service import ContentAssetService
from app.application.content.job_service import ContentIngestionJobService
from app.application.content.source_service import ContentSourceService
from app.application.curriculum.benchmark_service import (
    BenchmarkCurriculumService,
)
from app.application.curriculum.curriculum_source_service import (
    CurriculumSourceService,
)
from app.application.curriculum.institutional_adoption_service import (
    InstitutionalAdoptionService,
)
from app.application.identity.ports.email_sender import EmailSender
from app.application.identity.throttle import AuthThrottle
from app.application.identity.user_service import UserService
from app.application.tenant.invitation_service import TenantInvitationService
from app.application.tenant.join_service import TenantJoinService
from app.application.tenant.membership_service import TenantMembershipService
from app.core.config import STRICT_ENVIRONMENTS, settings
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
from app.infrastructure.content.unit_of_work import (
    ContentUnitOfWork,
    content_unit_of_work,
)
from app.infrastructure.curriculum.unit_of_work import (
    CurriculumUnitOfWork,
    curriculum_unit_of_work,
)
from app.infrastructure.email.outbox_email_sender import (
    OutboxEmailSender,
    UnconfiguredEmailSender,
)
from app.infrastructure.identity.security_event_recorder import (
    SQLAlchemySecurityEventRecorder,
)
from app.infrastructure.identity.unit_of_work import (
    IdentityUnitOfWork,
    identity_unit_of_work,
)
from app.infrastructure.ratelimit.fallback_counter_store import (
    FallbackCounterStore,
)
from app.infrastructure.ratelimit.memory_counter_store import InMemoryCounterStore
from app.infrastructure.ratelimit.redis_counter_store import RedisCounterStore
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService
from app.infrastructure.tenant.membership_unit_of_work import (
    TenantMembershipUnitOfWork,
)

ServiceT = TypeVar("ServiceT")


def build_email_sender() -> EmailSender:
    # The outbox keeps one-time codes in memory/on disk, so it is never used
    # in staging or production. No real provider is wired yet.
    if settings.app_environment in STRICT_ENVIRONMENTS:
        return UnconfiguredEmailSender()
    return OutboxEmailSender(settings.email_outbox_path)


def build_auth_throttle() -> AuthThrottle:
    # Tests run without Redis; every other environment shares counters
    # through Redis so limits hold across replicas.
    if settings.app_environment == "testing":
        return AuthThrottle(InMemoryCounterStore())
    return AuthThrottle(
        FallbackCounterStore(
            RedisCounterStore.from_url(settings.redis_url),
            mode=settings.auth_rate_limit_failure_mode,
        )
    )


@functools.cache
def shared_email_sender() -> EmailSender:
    """One sender per process, so every API module uses the same outbox."""
    return build_email_sender()


@functools.cache
def shared_auth_throttle() -> AuthThrottle:
    """One throttle per process, so limits are not split between modules."""
    return build_auth_throttle()


class Container:
    def __init__(self) -> None:
        self._services: dict[type[object], object] = {}

    def register(self, service_type: type[ServiceT], implementation: ServiceT) -> None:
        self._services[service_type] = implementation

    def get(self, service_type: type[ServiceT]) -> ServiceT:
        if service_type not in self._services:
            raise KeyError(f"Service {service_type.__name__} is not registered")
        return cast(ServiceT, self._services[service_type])


def build_container() -> Container:
    container = Container()
    event_bus = EventBus()
    password_hasher = Argon2PasswordHasher()
    token_service = JWTTokenService()
    email_sender = shared_email_sender()
    security_events = SQLAlchemySecurityEventRecorder(SessionLocal)
    container.register(SQLAlchemySecurityEventRecorder, security_events)
    container.register(AuthThrottle, shared_auth_throttle())

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
            email_sender=email_sender,
            security_events=security_events,
        ),
    )
    container.register(
        TenantInvitationService,
        TenantInvitationService(
            uow_factory=sqlalchemy_tenant_membership_uow,
            email_sender=email_sender,
            security_events=security_events,
        ),
    )
    container.register(
        TenantMembershipService,
        TenantMembershipService(
            uow_factory=sqlalchemy_tenant_membership_uow,
            security_events=security_events,
        ),
    )
    container.register(
        TenantJoinService,
        TenantJoinService(
            uow_factory=sqlalchemy_tenant_membership_uow,
            security_events=security_events,
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
    container.register(
        AssessmentService,
        AssessmentService(uow_factory=sqlalchemy_assessment_uow),
    )
    container.register(
        AttemptService,
        AttemptService(uow_factory=sqlalchemy_assessment_uow),
    )
    container.register(
        AttemptAnswerService,
        AttemptAnswerService(uow_factory=sqlalchemy_assessment_uow),
    )
    container.register(CurriculumUnitOfWork, sqlalchemy_curriculum_uow)
    container.register(
        CurriculumSourceService,
        CurriculumSourceService(
            event_bus=event_bus,
            uow_factory=sqlalchemy_curriculum_uow,
        ),
    )
    container.register(
        BenchmarkCurriculumService,
        BenchmarkCurriculumService(
            event_bus=event_bus,
            uow_factory=sqlalchemy_curriculum_uow,
        ),
    )
    container.register(
        InstitutionalAdoptionService,
        InstitutionalAdoptionService(
            event_bus=event_bus,
            uow_factory=sqlalchemy_curriculum_uow,
        ),
    )
    container.register(ContentUnitOfWork, sqlalchemy_content_uow)
    container.register(
        ContentSourceService,
        ContentSourceService(
            event_bus=event_bus,
            uow_factory=sqlalchemy_content_uow,
        ),
    )
    container.register(
        ContentAssetService,
        ContentAssetService(
            event_bus=event_bus,
            uow_factory=sqlalchemy_content_uow,
        ),
    )
    container.register(
        ContentIngestionJobService,
        ContentIngestionJobService(
            event_bus=event_bus,
            uow_factory=sqlalchemy_content_uow,
            security_events=security_events,
        ),
    )
    return container


@asynccontextmanager
async def sqlalchemy_identity_uow() -> AsyncIterator[IdentityUnitOfWork]:
    async with SessionLocal() as session:
        async with identity_unit_of_work(session) as uow:
            yield uow


@asynccontextmanager
async def sqlalchemy_tenant_membership_uow() -> AsyncIterator[TenantMembershipUnitOfWork]:
    async with SessionLocal() as session:
        async with TenantMembershipUnitOfWork(session) as uow:
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


@asynccontextmanager
async def sqlalchemy_curriculum_uow() -> AsyncIterator[CurriculumUnitOfWork]:
    async with SessionLocal() as session:
        async with curriculum_unit_of_work(session) as uow:
            yield uow


@asynccontextmanager
async def sqlalchemy_content_uow() -> AsyncIterator[ContentUnitOfWork]:
    async with SessionLocal() as session:
        async with content_unit_of_work(session) as uow:
            yield uow


def build_sqlalchemy_container() -> Container:
    container = Container()
    event_bus = EventBus()
    password_hasher = Argon2PasswordHasher()
    token_service = JWTTokenService()
    email_sender = shared_email_sender()
    security_events = SQLAlchemySecurityEventRecorder(SessionLocal)
    container.register(SQLAlchemySecurityEventRecorder, security_events)
    container.register(AuthThrottle, shared_auth_throttle())

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
            email_sender=email_sender,
            security_events=security_events,
        ),
    )
    return container

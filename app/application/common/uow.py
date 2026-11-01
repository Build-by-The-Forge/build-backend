from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository
from app.domain.repositories.attempt_result import AttemptResultRepository
from app.domain.repositories.benchmark_audit import (
    BenchmarkAuditRepository,
)
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.domain.repositories.content_asset import ContentAssetRepository
from app.domain.repositories.content_job import ContentIngestionJobRepository, IngestionEventRepository
from app.domain.repositories.content_source import ContentSourceRepository
from app.domain.repositories.course import CourseRepository
from app.domain.repositories.curriculum_source import CurriculumSourceRepository
from app.domain.repositories.institutional_adoption import (
    InstitutionalAdoptionRepository,
)
from app.domain.repositories.question import QuestionRepository
from app.domain.repositories.refresh_token import RefreshTokenRepository
from app.domain.repositories.session import SessionRepository
from app.domain.repositories.user import UserRepository


class AssessmentUnitOfWorkPort(Protocol):
    @property
    def assessments(self) -> AssessmentRepository: ...

    @property
    def questions(self) -> QuestionRepository: ...

    @property
    def catalogue(self) -> CourseRepository: ...

    @property
    def attempts(self) -> AttemptRepository: ...

    @property
    def attempt_answers(self) -> AttemptAnswerRepository: ...

    @property
    def attempt_results(self) -> AttemptResultRepository: ...


class CourseUnitOfWorkPort(Protocol):
    @property
    def courses(self) -> CourseRepository: ...


class IdentityUnitOfWorkPort(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def sessions(self) -> SessionRepository: ...

    @property
    def refresh_tokens(self) -> RefreshTokenRepository: ...


class CurriculumUnitOfWorkPort(Protocol):
    @property
    def sources(self) -> CurriculumSourceRepository: ...

    @property
    def benchmarks(self) -> BenchmarkCurriculumRepository: ...

    @property
    def benchmark_audits(self) -> BenchmarkAuditRepository: ...

    @property
    def adoptions(self) -> InstitutionalAdoptionRepository: ...


class ContentUnitOfWorkPort(Protocol):
    @property
    def sources(self) -> ContentSourceRepository: ...

    @property
    def assets(self) -> ContentAssetRepository: ...

    @property
    def jobs(self) -> ContentIngestionJobRepository: ...

    @property
    def ingestion_events(self) -> IngestionEventRepository: ...


AssessmentUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[AssessmentUnitOfWorkPort]]
CourseUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[CourseUnitOfWorkPort]]
IdentityUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[IdentityUnitOfWorkPort]]
CurriculumUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[CurriculumUnitOfWorkPort]]
ContentUnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[ContentUnitOfWorkPort]]

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository
from app.domain.repositories.attempt_result import AttemptResultRepository
from app.domain.repositories.course import CourseRepository
from app.domain.repositories.question import QuestionRepository
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


AssessmentUnitOfWorkFactory = Callable[
    [], AbstractAsyncContextManager[AssessmentUnitOfWorkPort]
]
CourseUnitOfWorkFactory = Callable[
    [], AbstractAsyncContextManager[CourseUnitOfWorkPort]
]
IdentityUnitOfWorkFactory = Callable[
    [], AbstractAsyncContextManager[IdentityUnitOfWorkPort]
]

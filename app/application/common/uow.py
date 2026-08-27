from collections.abc import Callable
from typing import AsyncContextManager, Protocol

from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.course import CourseRepository
from app.domain.repositories.question import QuestionRepository
from app.domain.repositories.session import SessionRepository
from app.domain.repositories.user import UserRepository


class AssessmentUnitOfWorkPort(Protocol):
    assessments: AssessmentRepository
    questions: QuestionRepository
    catalogue: CourseRepository


class CourseUnitOfWorkPort(Protocol):
    courses: CourseRepository


class IdentityUnitOfWorkPort(Protocol):
    users: UserRepository
    sessions: SessionRepository


AssessmentUnitOfWorkFactory = Callable[
    [], AsyncContextManager[AssessmentUnitOfWorkPort]
]
CourseUnitOfWorkFactory = Callable[[], AsyncContextManager[CourseUnitOfWorkPort]]
IdentityUnitOfWorkFactory = Callable[[], AsyncContextManager[IdentityUnitOfWorkPort]]

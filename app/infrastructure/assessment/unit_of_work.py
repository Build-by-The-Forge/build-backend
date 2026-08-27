from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.assessment.repositories import (
    SqlAlchemyAssessmentRepository,
    SqlAlchemyQuestionRepository,
)
from app.infrastructure.catalogue.repositories import SqlAlchemyCourseRepository
from app.infrastructure.unit_of_work import UnitOfWork


class AssessmentUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.assessments = SqlAlchemyAssessmentRepository(session)
        self.questions = SqlAlchemyQuestionRepository(session)
        self.catalogue = SqlAlchemyCourseRepository(session)


@asynccontextmanager
async def assessment_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[AssessmentUnitOfWork]:
    async with AssessmentUnitOfWork(session) as uow:
        yield uow

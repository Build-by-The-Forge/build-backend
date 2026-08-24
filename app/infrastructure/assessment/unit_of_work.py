from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.assessment.repositories import SqlAlchemyQuestionRepository
from app.infrastructure.unit_of_work import UnitOfWork


class AssessmentUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.questions = SqlAlchemyQuestionRepository(session)
        self.catalogue = None


@asynccontextmanager
async def assessment_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[AssessmentUnitOfWork]:
    async with AssessmentUnitOfWork(session) as uow:
        yield uow

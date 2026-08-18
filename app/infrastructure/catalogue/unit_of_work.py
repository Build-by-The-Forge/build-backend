from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.catalogue.repositories import SqlAlchemyCourseRepository
from app.infrastructure.unit_of_work import UnitOfWork


class CourseUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.courses = SqlAlchemyCourseRepository(session)


@asynccontextmanager
async def catalogue_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[CourseUnitOfWork]:
    async with CourseUnitOfWork(session) as uow:
        yield uow

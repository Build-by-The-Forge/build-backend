from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.infrastructure.curriculum.adoption_repositories import (
    SqlAlchemyInstitutionalAdoptionRepository,
)
from app.infrastructure.curriculum.audit_repositories import (
    SqlAlchemyBenchmarkAuditRepository,
)
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)
from app.infrastructure.unit_of_work import UnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession


class CurriculumUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.sources = SqlAlchemyCurriculumSourceRepository(session)
        self.benchmarks = SqlAlchemyBenchmarkCurriculumRepository(session)
        self.benchmark_audits = SqlAlchemyBenchmarkAuditRepository(session)
        self.adoptions = SqlAlchemyInstitutionalAdoptionRepository(session)


@asynccontextmanager
async def curriculum_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[CurriculumUnitOfWork]:
    async with CurriculumUnitOfWork(session) as uow:
        yield uow

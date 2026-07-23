from collections.abc import AsyncIterator

from app.db.session import SessionLocal
from app.infrastructure.unit_of_work import UnitOfWork


async def get_unit_of_work() -> AsyncIterator[UnitOfWork]:
    async with SessionLocal() as session:
        async with UnitOfWork(session) as uow:
            yield uow

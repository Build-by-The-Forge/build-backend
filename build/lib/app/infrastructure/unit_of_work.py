from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def close(self) -> None:
        await self.session.close()


@asynccontextmanager
async def unit_of_work(session: AsyncSession) -> AsyncIterator[UnitOfWork]:
    uow = UnitOfWork(session)
    try:
        yield uow
        await uow.commit()
    except Exception:
        await uow.rollback()
        raise
    finally:
        await uow.close()

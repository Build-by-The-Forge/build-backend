from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Self

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            logger.error(
                "unit_of_work_rollback",
                exception_type=exc_type.__name__,
                exception=str(exc_value),
            )
            try:
                await self.rollback()
            except Exception:
                logger.exception("unit_of_work_rollback_failed")
                raise
        else:
            try:
                await self.commit()
            except Exception:
                logger.exception("unit_of_work_commit_failed")
                try:
                    await self.rollback()
                except Exception:
                    logger.exception("unit_of_work_rollback_after_commit_failed")
                raise
        try:
            await self.close()
        except Exception:
            logger.exception("unit_of_work_close_failed")
            raise

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def close(self) -> None:
        await self.session.close()


@asynccontextmanager
async def unit_of_work(session: AsyncSession) -> AsyncIterator[UnitOfWork]:
    async with UnitOfWork(session) as uow:
        yield uow

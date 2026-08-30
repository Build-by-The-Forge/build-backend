from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.content.asset_repositories import (
    SqlAlchemyContentAssetRepository,
)
from app.infrastructure.content.repositories import SqlAlchemyContentSourceRepository
from app.infrastructure.unit_of_work import UnitOfWork


class ContentUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.sources = SqlAlchemyContentSourceRepository(session)
        self.assets = SqlAlchemyContentAssetRepository(session)


@asynccontextmanager
async def content_unit_of_work(
    session: AsyncSession,
) -> AsyncIterator[ContentUnitOfWork]:
    async with ContentUnitOfWork(session) as uow:
        yield uow

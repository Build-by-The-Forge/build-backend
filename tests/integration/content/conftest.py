from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.infrastructure.content.unit_of_work import ContentUnitOfWork


@pytest.fixture
def uow_factory(engine: AsyncEngine):
    """A ContentUnitOfWork per call, on the test schema."""
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    @asynccontextmanager
    async def factory() -> AsyncIterator[ContentUnitOfWork]:
        async with maker() as session:
            async with ContentUnitOfWork(session) as uow:
                yield uow

    return factory

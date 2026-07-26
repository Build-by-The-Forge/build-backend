import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.infrastructure.identity.models import UserModel, SessionModel


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    database_url = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(database_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="function")
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
        await session.rollback()

# tests/conftest.py
import asyncio
import os
from collections.abc import AsyncIterator

os.environ["APP_ENVIRONMENT"] = "testing"

import pytest
from app.db.base import Base
from app.db.session import engine as app_engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture(scope="session", autouse=True)
async def prepare_app_database():
    """Tables for TestClient - uses the app's own engine"""
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """Separate in-memory engine for pure repository integration tests"""
    database_url = "sqlite+aiosqlite:///:memory:"
    eng = create_async_engine(database_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session() as sess:
        yield sess
        await sess.rollback()

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from tests.integration.content.uploads import BUCKET, InMemoryStorage


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


@pytest.fixture(autouse=True)
def managed_storage(monkeypatch) -> InMemoryStorage:
    """One in-memory object store behind both the upload service and the
    dispatch check, with a configured bucket: assets are created through the
    upload endpoint and only managed objects are dispatched (P3-1 PR 3b).
    Tests that need their own store patch over this one."""
    from app.api.content import assets as assets_api
    from app.api.content import jobs as jobs_api
    from app.core.config import settings

    storage = InMemoryStorage()
    monkeypatch.setattr(settings, "object_storage_bucket", BUCKET)
    monkeypatch.setattr(assets_api.upload_service, "_storage_factory", lambda: storage)
    monkeypatch.setattr(jobs_api.service, "_storage_factory", lambda: storage)
    return storage

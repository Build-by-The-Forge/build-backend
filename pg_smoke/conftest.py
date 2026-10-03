"""Smoke tests against a PostgreSQL database built only by migrations.

Requires POSTGRES_URL (and the same URL as DATABASE_URL for Alembic) pointing
at a database already migrated with `alembic upgrade head`. Nothing here
calls create_all: the point is to exercise the schema production gets.
"""

import os

# Must run before the app is imported: "testing" would swap in SQLite.
os.environ["APP_ENVIRONMENT"] = "development"

import pytest  # noqa: E402

if not os.environ.get("POSTGRES_URL", "").startswith("postgresql"):
    pytest.skip("POSTGRES_URL must point at a migrated PostgreSQL database", allow_module_level=True)

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    # No lifespan is run, so the app never creates tables itself.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as c:
        yield c

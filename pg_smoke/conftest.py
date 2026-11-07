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


@pytest.fixture(autouse=True)
def reset_auth_rate_limits():
    """Each test starts with clean auth rate-limit counters, as in tests/.

    The smoke suite registers and signs in many accounts from one address,
    which would otherwise exhaust the per-IP limits it is not testing.
    """
    import redis

    from app.bootstrap.container import shared_auth_throttle

    client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    try:
        keys = list(client.scan_iter("auth:*"))
        if keys:
            client.delete(*keys)
    except redis.exceptions.RedisError:
        pass  # Redis absent: the throttle runs on its local fallback
    finally:
        client.close()
    local = getattr(shared_auth_throttle().store, "_local", None)
    if local is not None:
        local.reset()
    yield


def pytest_configure(config):
    config.addinivalue_line("markers", "real_scanning: new documents stay quarantined until a real scan verdict")


@pytest.fixture(autouse=True)
def scan_stand_in(request, monkeypatch):
    """New documents pass a stand-in scan unless the test is marked
    real_scanning (tests/scan_stand_in.py)."""
    from tests.scan_stand_in import stand_in_unless_real_scanning

    stand_in_unless_real_scanning(request, monkeypatch)


@pytest.fixture(autouse=True)
def _registrations_complete_inline(monkeypatch):
    """These suites have no worker process. Set on the object, not the environment, so
    a test building its own production Settings isn't affected."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "registration_inline_for_tests", True)

import os

os.environ["APP_ENVIRONMENT"] = "testing"

import pytest


def pytest_configure(config):
    """The application's logging configuration, for every test.

    app.main applies it when imported, so without this a test's log
    output depended on whether an earlier test happened to import app.main:
    run alone, structlog stayed on its default print logger and caplog saw
    nothing. Applying it once here makes every selection see the
    production configuration.
    """
    from app.core.logging import configure_logging

    configure_logging()


@pytest.fixture(autouse=True)
def learning_memory_enabled(monkeypatch):
    """Tests run with memory on, as development can; tests of the closed gate
    turn it off themselves. On the settings object, not the environment, so a
    test building its own Settings still starts from the default (off)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "learning_memory_enabled", True)


@pytest.fixture(autouse=True)
def reset_auth_rate_limits():
    """Each test starts with fresh auth rate-limit counters."""
    from app.api import identity as identity_api
    from app.infrastructure.ratelimit.memory_counter_store import InMemoryCounterStore

    store = identity_api.throttle.store
    if isinstance(store, InMemoryCounterStore):
        store.reset()
    yield

import os

os.environ["APP_ENVIRONMENT"] = "testing"

import pytest


@pytest.fixture(autouse=True)
def reset_auth_rate_limits():
    """Each test starts with fresh auth rate-limit counters."""
    from app.api import identity as identity_api
    from app.infrastructure.ratelimit.memory_counter_store import InMemoryCounterStore

    store = identity_api.throttle.store
    if isinstance(store, InMemoryCounterStore):
        store.reset()
    yield

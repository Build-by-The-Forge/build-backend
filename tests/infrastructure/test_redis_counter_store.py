"""Runs against a real Redis: set TEST_REDIS_URL (e.g. redis://127.0.0.1:6379/15)."""

import asyncio
import os
from uuid import uuid4

import pytest

from app.application.identity.throttle import LOGIN_FAILURES_PER_PAIR, AuthThrottle
from app.core.exceptions import RateLimitedError
from app.infrastructure.ratelimit.fallback_counter_store import FallbackCounterStore
from app.infrastructure.ratelimit.redis_counter_store import RedisCounterStore

REDIS_URL = os.getenv("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")


@pytest.fixture
async def store():
    store = RedisCounterStore.from_url(REDIS_URL, timeout_seconds=2)
    yield store
    await store.close()


def _key():
    return f"test:{uuid4().hex}"


async def test_concurrent_hits_each_get_a_distinct_count(store):
    key = _key()

    results = await asyncio.gather(*[store.hit(key, 60) for _ in range(50)])

    assert sorted(count for count, _ in results) == list(range(1, 51))
    assert all(0 < ttl <= 60 for _, ttl in results)


async def test_later_hits_do_not_extend_the_window(store):
    key = _key()
    await store.hit(key, 2)
    await asyncio.sleep(1.1)

    _, ttl = await store.hit(key, 2)

    assert ttl == 1


async def test_window_rolls_over_after_expiry(store):
    key = _key()
    await store.hit(key, 1)
    await store.hit(key, 1)
    await asyncio.sleep(1.2)

    assert (await store.hit(key, 1))[0] == 1


async def test_lock_expires_and_can_be_cleared(store):
    key = _key()
    assert await store.lock_ttl(key) == 0

    await store.lock(key, 1)
    assert await store.lock_ttl(key) == 1
    await asyncio.sleep(1.2)
    assert await store.lock_ttl(key) == 0

    await store.lock(key, 60)
    await store.clear(key)
    assert await store.lock_ttl(key) == 0


async def test_concurrent_wrong_passwords_lock_the_pair_through_redis(store):
    throttle = AuthThrottle(store, prefix=f"test:{uuid4().hex}")
    email, ip = "victim@example.com", "10.0.0.1"

    async def guess():
        try:
            attempt = await throttle.before_login(email, ip)
        except RateLimitedError:
            return False
        await throttle.login_failed(attempt)
        return True

    admitted = await asyncio.gather(*[guess() for _ in range(30)])

    assert sum(admitted) == LOGIN_FAILURES_PER_PAIR.limit
    with pytest.raises(RateLimitedError):
        await throttle.before_login(email, ip)
    await throttle.before_login("bystander@example.com", ip)


async def test_limits_are_shared_between_two_app_instances(store):
    """Two replicas (two clients) see one counter."""
    other = RedisCounterStore.from_url(REDIS_URL, timeout_seconds=2)
    prefix = f"test:{uuid4().hex}"
    a, b = AuthThrottle(store, prefix=prefix), AuthThrottle(other, prefix=prefix)
    try:
        for i in range(LOGIN_FAILURES_PER_PAIR.limit):
            replica = a if i % 2 else b
            attempt = await replica.before_login("victim@example.com", "10.0.0.1")
            await replica.login_failed(attempt)

        with pytest.raises(RateLimitedError):
            await a.before_login("victim@example.com", "10.0.0.1")
    finally:
        await other.close()


async def test_unreachable_redis_falls_back_without_hanging():
    dead = RedisCounterStore.from_url("redis://127.0.0.1:1/0", timeout_seconds=0.25)
    store = FallbackCounterStore(dead, mode="local")

    counts = await asyncio.wait_for(
        asyncio.gather(*[store.hit("k", 60) for _ in range(3)]), timeout=5
    )

    assert sorted(c for c, _ in counts) == [1, 2, 3]

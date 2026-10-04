import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.application.identity.ports.counter_store import CounterStoreUnavailable
from app.infrastructure.ratelimit.fallback_counter_store import FallbackCounterStore
from app.infrastructure.ratelimit.memory_counter_store import InMemoryCounterStore


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class DownStore:
    """A Redis store whose server is unreachable."""

    def __init__(self) -> None:
        self.calls = 0

    async def _fail(self, *args):
        self.calls += 1
        raise RedisConnectionError("connection refused")

    hit = lock = lock_ttl = clear = _fail


async def test_memory_counts_within_a_window_and_rolls_over():
    clock = Clock()
    store = InMemoryCounterStore(clock)

    assert await store.hit("k", 60) == (1, 60)
    clock.now += 59
    assert await store.hit("k", 60) == (2, 1)
    clock.now += 1
    assert await store.hit("k", 60) == (1, 60)  # new window


async def test_memory_locks_expire_and_can_be_cleared():
    clock = Clock()
    store = InMemoryCounterStore(clock)

    await store.lock("l", 30)
    assert await store.lock_ttl("l") == 30
    clock.now += 30
    assert await store.lock_ttl("l") == 0

    await store.lock("l", 30)
    await store.clear("l")
    assert await store.lock_ttl("l") == 0


async def test_fallback_keeps_enforcing_with_local_counters_when_redis_is_down():
    primary = DownStore()
    store = FallbackCounterStore(primary, mode="local", clock=Clock())

    counts = [(await store.hit("k", 60))[0] for _ in range(3)]

    assert counts == [1, 2, 3]
    assert primary.calls == 1  # skipped during the retry window


async def test_fallback_retries_redis_after_the_retry_window():
    clock = Clock()
    primary = DownStore()
    store = FallbackCounterStore(primary, mode="local", retry_seconds=5, clock=clock)

    await store.hit("k", 60)
    clock.now += 5
    await store.hit("k", 60)

    assert primary.calls == 2


async def test_fallback_in_closed_mode_refuses_when_redis_is_down():
    store = FallbackCounterStore(DownStore(), mode="closed", clock=Clock())

    with pytest.raises(CounterStoreUnavailable):
        await store.hit("k", 60)
    with pytest.raises(CounterStoreUnavailable):  # also while skipping Redis
        await store.lock_ttl("k")


async def test_fallback_uses_redis_when_it_is_healthy():
    primary = InMemoryCounterStore()
    local = InMemoryCounterStore()
    store = FallbackCounterStore(primary, local=local)

    await store.hit("k", 60)

    assert await primary.hit("k", 60) == (2, 60)
    assert await local.hit("k", 60) == (1, 60)

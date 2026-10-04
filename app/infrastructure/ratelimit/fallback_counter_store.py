import logging
import time
from collections.abc import Awaitable, Callable
from typing import Literal, TypeVar

from redis.exceptions import RedisError

from app.application.identity.ports.counter_store import (
    CounterStore,
    CounterStoreUnavailable,
)
from app.infrastructure.ratelimit.memory_counter_store import InMemoryCounterStore

logger = logging.getLogger(__name__)

T = TypeVar("T")
FailureMode = Literal["local", "closed"]


class FallbackCounterStore:
    """Redis first; on a Redis failure, apply the configured failure mode.

    ``local``  - keep enforcing limits with per-process counters (default).
    ``closed`` - refuse the request (CounterStoreUnavailable).
    There is deliberately no fail-open mode: abuse controls never silently
    switch off.

    After a failure Redis is skipped for ``retry_seconds`` so an outage does
    not add a connection timeout to every request.
    """

    def __init__(
        self,
        primary: CounterStore,
        mode: FailureMode = "local",
        local: InMemoryCounterStore | None = None,
        retry_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._mode = mode
        self._local = local or InMemoryCounterStore()
        self._retry_seconds = retry_seconds
        self._clock = clock
        self._skip_primary_until = 0.0

    async def _call(
        self,
        primary: Callable[[], Awaitable[T]],
        local: Callable[[], Awaitable[T]],
    ) -> T:
        if self._clock() >= self._skip_primary_until:
            try:
                return await primary()
            except (RedisError, OSError, TimeoutError) as exc:
                self._skip_primary_until = self._clock() + self._retry_seconds
                logger.error(
                    "rate-limit store unavailable (%s); failure mode %r",
                    type(exc).__name__,
                    self._mode,
                )
        if self._mode == "closed":
            raise CounterStoreUnavailable()
        return await local()

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        return await self._call(
            lambda: self._primary.hit(key, window_seconds),
            lambda: self._local.hit(key, window_seconds),
        )

    async def lock(self, key: str, seconds: int) -> None:
        await self._call(
            lambda: self._primary.lock(key, seconds),
            lambda: self._local.lock(key, seconds),
        )

    async def lock_ttl(self, key: str) -> int:
        return await self._call(
            lambda: self._primary.lock_ttl(key),
            lambda: self._local.lock_ttl(key),
        )

    async def clear(self, *keys: str) -> None:
        await self._call(
            lambda: self._primary.clear(*keys),
            lambda: self._local.clear(*keys),
        )

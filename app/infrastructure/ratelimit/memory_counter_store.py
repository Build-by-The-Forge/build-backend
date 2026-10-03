import math
import time
from collections.abc import Callable


class InMemoryCounterStore:
    """Per-process counters: used in tests and as the Redis-outage fallback.

    Limits are enforced per process only, so with several replicas the
    effective limit is multiplied; still far better than no limit.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 100_000) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._entries: dict[str, tuple[int, float]] = {}

    def _live(self, key: str) -> tuple[int, float] | None:
        entry = self._entries.get(key)
        if entry is not None and entry[1] <= self._clock():
            del self._entries[key]
            return None
        return entry

    def _prune(self) -> None:
        if len(self._entries) < self._max_keys:
            return
        now = self._clock()
        for key in [k for k, (_, exp) in self._entries.items() if exp <= now]:
            del self._entries[key]

    def _seconds_left(self, expires_at: float) -> int:
        return max(math.ceil(expires_at - self._clock()), 1)

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        entry = self._live(key)
        if entry is None:
            self._prune()
            entry = (0, self._clock() + window_seconds)
        count, expires_at = entry[0] + 1, entry[1]
        self._entries[key] = (count, expires_at)
        return count, self._seconds_left(expires_at)

    async def lock(self, key: str, seconds: int) -> None:
        self._prune()
        self._entries[key] = (1, self._clock() + seconds)

    async def lock_ttl(self, key: str) -> int:
        entry = self._live(key)
        return 0 if entry is None else self._seconds_left(entry[1])

    async def clear(self, *keys: str) -> None:
        for key in keys:
            self._entries.pop(key, None)

    def reset(self) -> None:
        self._entries.clear()

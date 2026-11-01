from typing import Protocol


class CounterStoreUnavailable(Exception):
    """The counter backend cannot be reached and no fallback is allowed."""


class CounterStore(Protocol):
    """Expiring counters and locks for abuse controls.

    ``hit`` must be atomic: concurrent callers each see a distinct count.
    """

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Increment ``key``; start its window on first hit. Return (count, seconds left)."""
        ...

    async def lock(self, key: str, seconds: int) -> None: ...

    async def lock_ttl(self, key: str) -> int:
        """Seconds until ``key``'s lock expires, or 0 if it is not locked."""
        ...

    async def clear(self, *keys: str) -> None: ...

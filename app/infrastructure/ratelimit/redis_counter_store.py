from redis.asyncio import Redis


class RedisCounterStore:
    """Fixed-window counters and TTL locks in Redis (shared by all replicas)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str, timeout_seconds: float = 0.5) -> "RedisCounterStore":
        # Short timeouts: an unreachable Redis must not stall sign-in requests.
        return cls(
            Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=timeout_seconds,
                socket_timeout=timeout_seconds,
            )
        )

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        # INCR and EXPIRE NX in one MULTI: the window starts on the first hit
        # and later hits never extend it.
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            pipe.ttl(key)
            count, _, ttl = await pipe.execute()
        return int(count), max(int(ttl), 1)

    async def lock(self, key: str, seconds: int) -> None:
        await self._redis.set(key, "1", ex=seconds)

    async def lock_ttl(self, key: str) -> int:
        return max(int(await self._redis.ttl(key)), 0)

    async def clear(self, *keys: str) -> None:
        if keys:
            await self._redis.delete(*keys)

    async def close(self) -> None:
        await self._redis.aclose()

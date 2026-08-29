from redis.asyncio import Redis

from app.core.config import settings


class RedisClient:
    def __init__(self, url: str | None = None) -> None:
        self._redis = Redis.from_url(url or settings.redis_url, decode_responses=True)

    async def ping(self) -> bool:
        return await self._redis.ping()

    async def close(self) -> None:
        await self._redis.close()

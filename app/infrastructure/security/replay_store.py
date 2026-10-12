"""Replay protection for BUILD Service Signature v1 (design A.5 step 8)."""

from redis.asyncio import Redis
from redis.exceptions import RedisError

# Longer than the whole +/-60 s acceptance window, so a request id cannot be
# reused before its timestamp has gone stale.
REPLAY_TTL_SECONDS = 180


class ReplayStoreUnavailable(Exception):
    """Redis could not be reached; the receiver fails closed with 503."""


class RedisReplayStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str, timeout_seconds: float = 0.5) -> "RedisReplayStore":
        return cls(
            Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=timeout_seconds,
                socket_timeout=timeout_seconds,
            )
        )

    @staticmethod
    def key(receiver: str, sender: str, request_id: str) -> str:
        return f"svcauth:{receiver}:{sender}:{request_id}"

    async def claim(self, receiver: str, sender: str, request_id: str) -> bool:
        """True the first time a request id is seen, False on any reuse."""
        try:
            created = await self._redis.set(self.key(receiver, sender, request_id), "1", nx=True, ex=REPLAY_TTL_SECONDS)
        except (RedisError, OSError) as exc:
            raise ReplayStoreUnavailable(str(exc)) from exc
        return bool(created)

    async def close(self) -> None:
        await self._redis.aclose()

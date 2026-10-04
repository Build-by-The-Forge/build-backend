"""Inbound BUILD Service Signature v1 verification (design A.5).

An ASGI middleware rather than a dependency: FastAPI reads the whole body
before dependencies run, but the 1 MiB limit must be enforced while the body
is being consumed. For a protected path it runs, in order:

1-5  headers, sender, timestamp, request id, context      -> 401
6    streamed body limit, hashed incrementally             -> 413
7    signature (current, then previous secret)             -> 401
8    replay claim in Redis, only after a valid signature   -> 401, or 503 if
     Redis is unavailable (fail closed)

Only then does the route run, with the buffered body replayed to it and the
verified request on ``request.state.service_auth``. Every 401 has the same
body; the reason is logged, never returned.
"""

import hashlib
import time
from collections.abc import Callable
from typing import Any, Protocol

import structlog
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.infrastructure.security.replay_store import ReplayStoreUnavailable
from app.infrastructure.security.service_signature import (
    Direction,
    ServiceAuthError,
    ServiceKeys,
    check_headers,
    check_signature,
    request_target,
)

logger = structlog.get_logger(__name__)

MAX_BODY_BYTES = 1024 * 1024
STATE_KEY = "service_auth"


class ReplayStore(Protocol):
    async def claim(self, receiver: str, sender: str, request_id: str) -> bool: ...


class _BodyTooLarge(Exception):
    pass


class _ClientDisconnected(Exception):
    pass


class ServiceAuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        receiver: str,
        direction: Direction,
        keys: ServiceKeys,
        replay_store: ReplayStore,
        is_protected: Callable[[str], bool],
        max_body_bytes: int = MAX_BODY_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self.receiver = receiver
        self.direction = direction
        self.keys = keys
        self.replay_store = replay_store
        self.is_protected = is_protected
        self.max_body_bytes = max_body_bytes
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.is_protected(scope["path"]):
            await self.app(scope, receive, send)
            return

        try:
            checked = check_headers(
                direction=self.direction, headers=Headers(scope=scope), now=int(self.clock())
            )
            target = request_target(
                scope.get("raw_path") or scope["path"].encode("ascii", "replace"),
                scope.get("query_string", b""),
            )
        except ServiceAuthError as exc:
            await self._reject(scope, receive, send, 401, exc.reason)
            return

        try:
            body = await self._read_body(scope, receive)
        except _BodyTooLarge:
            await self._reject(scope, receive, send, 413, "body exceeds limit")
            return
        except _ClientDisconnected:
            return

        try:
            verified = check_signature(
                checked,
                keys=self.keys,
                method=scope["method"],
                target=target,
                body_sha256=hashlib.sha256(body).hexdigest(),
            )
        except ServiceAuthError as exc:
            await self._reject(scope, receive, send, 401, exc.reason)
            return

        try:
            fresh = await self.replay_store.claim(
                self.receiver, verified.service, verified.request_id
            )
        except ReplayStoreUnavailable as exc:
            await self._reject(scope, receive, send, 503, f"replay store unavailable: {exc}")
            return
        if not fresh:
            await self._reject(scope, receive, send, 401, "request id replayed")
            return

        scope.setdefault("state", {})[STATE_KEY] = verified
        await self.app(scope, _replay(body, receive), send)

    async def _read_body(self, scope: Scope, receive: Receive) -> bytes:
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes:
            raise _BodyTooLarge
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise _ClientDisconnected
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body_bytes:
                raise _BodyTooLarge  # stop reading; nothing more is consumed
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def _reject(
        self, scope: Scope, receive: Receive, send: Send, status: int, reason: str
    ) -> None:
        logger.warning(
            "service_auth_rejected",
            status_code=status,
            reason=reason,
            path=scope["path"],
            receiver=self.receiver,
        )
        message: dict[str, Any] = {
            401: {"error": "invalid service authentication"},
            413: {"error": "request body too large"},
            503: {"error": "service temporarily unavailable"},
        }[status]
        await JSONResponse(message, status_code=status)(scope, receive, send)


def _replay(body: bytes, receive: Receive) -> Receive:
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay

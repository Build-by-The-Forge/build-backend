"""Request body size limit for every route (plan §8.4, M6), with optional
per-route limits for routes that legitimately take larger bodies (document
uploads, P3-1 PR 2).

Pure ASGI so it sees the body as it streams: a declared Content-Length over
the limit is refused before the app runs; a body that grows past the limit
while being read (chunked or lying about its length) is cut off with 413 as
long as no response has started. The signed callback route keeps its own,
equal limit inside ServiceAuthMiddleware.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY = json.dumps({"success": False, "data": {}, "meta": {"error": "request body too large"}}).encode()


class _TooLarge(Exception):
    pass


class RouteBodyLimit:
    """A different limit for one method and path. The pattern must match the
    whole path; every other request keeps the global limit."""

    def __init__(self, method: str, path_pattern: str, max_body_bytes: int) -> None:
        self.method = method.upper()
        self.path = re.compile(path_pattern)
        self.max_body_bytes = max_body_bytes

    def matches(self, scope: Scope) -> bool:
        return str(scope.get("method", "")).upper() == self.method and self.path.fullmatch(str(scope.get("path", ""))) is not None


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int, route_limits: Sequence[RouteBodyLimit] = ()) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.route_limits = tuple(route_limits)

    def _limit_for(self, scope: Scope) -> int:
        for route in self.route_limits:
            if route.matches(scope):
                return route.max_body_bytes
        return self.max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope)
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _reject(send)
            return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _reject(send)


async def _reject(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(_BODY)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": _BODY})

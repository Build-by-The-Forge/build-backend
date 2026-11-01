import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import error_response
from app.core.metrics import errors_total, requests_total
from app.core.request_context import RequestMeta, accepted_request_id, client_ip, current_request

logger = structlog.get_logger(__name__)


class UnhandledErrorMiddleware:
    """Answers a route's unexpected failure from inside the stack, so the response
    passes back through the request ID, security headers and CORS like any other.
    Once a response has started it can't be replaced, so that failure re-raises."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                raise
            request = Request(scope)
            request_id = getattr(request.state, "request_id", None)
            errors_total.labels(error_type=type(exc).__name__).inc()
            logger.exception("request_failed", request_id=request_id, method=request.method, path=request.url.path)
            response = error_response(request, 500, "INTERNAL_ERROR", "something went wrong")
            await response(scope, receive, send)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = accepted_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        request.state.start_time = time.perf_counter()
        context_token = current_request.set(
            RequestMeta(
                request_id=request_id,
                ip=client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        )

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            errors_total.labels(error_type=type(exc).__name__).inc()
            logger.exception(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
            )
            raise
        finally:
            requests_total.inc()
            current_request.reset(context_token)

        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = str(round((time.perf_counter() - request.state.start_time) * 1000, 3))
        return response

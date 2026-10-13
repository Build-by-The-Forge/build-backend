import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.metrics import errors_total, requests_total
from app.core.request_context import RequestMeta, client_ip, current_request

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
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

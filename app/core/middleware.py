import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.perf_counter()

        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = str(round((time.perf_counter() - request.state.start_time) * 1000, 3))
        return response

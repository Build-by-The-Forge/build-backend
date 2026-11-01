import uuid

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.metrics import errors_total
from app.core.security import SECURITY_HEADERS

logger = structlog.get_logger(__name__)

# What a client branches on when a raise names no specific code. The specific
# ones are in the contract's ErrorCode list. A code never changes meaning.
_CODE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "AUTH_TOKEN_INVALID",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "RESOURCE_NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_413_CONTENT_TOO_LARGE: "UPLOAD_TOO_LARGE",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_FAILED",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def code_for_status(status_code: int) -> str:
    return _CODE_BY_STATUS.get(status_code, "INTERNAL_ERROR" if status_code >= 500 else "BAD_REQUEST")


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        *,
        code: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code or code_for_status(status_code)
        super().__init__(message)


class RateLimitedError(AppError):
    """429 with a Retry-After hint. One message for every limit and lock, so
    the response never reveals which rule fired or whether an account exists."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("too many requests", status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        self.retry_after = max(int(retry_after), 1)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


def public_message(exc: Exception, fallback: str = "the request could not be completed") -> str:
    """Text for a client, from an exception a route expects. Only this application
    writes the messages of its own errors and of plain ValueError. A library's
    subclass (pydantic, unicode, JSON) can quote the input, so it gets the fallback."""
    kind = type(exc)
    if kind is ValueError or kind.__module__.startswith("app."):
        return str(exc)
    return fallback


def error_body(
    request_id: str | None,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
        "meta": {"request_id": request_id},
    }


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content=error_body(request_id, code, message, details),
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Starlette raises its own HTTPException (the base of FastAPI's) for
    # unmatched routes and methods; both must answer with their status.
    if not isinstance(exc, StarletteHTTPException):
        raise TypeError("expected HTTPException")
    request_id = getattr(request.state, "request_id", None)
    errors_total.labels(error_type="HTTPException").inc()
    logger.warning(
        "http_exception",
        request_id=request_id,
        status_code=exc.status_code,
        path=request.url.path,
    )
    return error_response(
        request,
        exc.status_code,
        code_for_status(exc.status_code),
        str(exc.detail),
        # Keep WWW-Authenticate (401), Allow (405) and similar headers.
        headers=dict(exc.headers) if exc.headers else None,
    )


def _safe_details(exc: RequestValidationError) -> dict[str, object]:
    """Where and why, never the refused value: it may be a password."""
    return {
        "fields": [
            {"field": ".".join(str(part) for part in e["loc"]), "code": e["type"], "message": e["msg"]} for e in exc.errors()
        ]
    }


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("expected RequestValidationError")
    request_id = getattr(request.state, "request_id", None)
    errors_total.labels(error_type="RequestValidationError").inc()
    logger.warning(
        "request_validation_failed",
        request_id=request_id,
        path=request.url.path,
    )
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "VALIDATION_FAILED",
        "validation failed",
        details=_safe_details(exc),
    )


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise TypeError("expected AppError")
    request_id = getattr(request.state, "request_id", None)
    errors_total.labels(error_type=type(exc).__name__).inc()
    logger.warning(
        "application_exception",
        request_id=request_id,
        status_code=exc.status_code,
        path=request.url.path,
    )
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimitedError) else None
    return error_response(request, exc.status_code, exc.code, exc.message, headers=headers)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The backstop for a failure in the middleware stack itself; a failure in a
    route is answered by UnhandledErrorMiddleware, inside CORS and the security
    headers. CORS can't apply here, since it may be what failed. The text stays in
    the log, and the client gets only the ID that finds it there."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    logger.error("request_failed_outside_routes", request_id=request_id, error_type=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(request_id, "INTERNAL_ERROR", "something went wrong"),
        headers={"x-request-id": request_id, **SECURITY_HEADERS},
    )

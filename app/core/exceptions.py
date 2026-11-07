import re
import uuid
from collections.abc import Collection, Iterable
from typing import Any

import structlog
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.metrics import errors_total
from app.core.security import SECURITY_HEADERS
from app.domain.client_safe import ClientMessage

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


# What a client reads when an error's own text isn't marked as written for clients.
_MESSAGE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "the request could not be completed",
    status.HTTP_401_UNAUTHORIZED: "authentication is required",
    status.HTTP_403_FORBIDDEN: "permission denied",
    status.HTTP_404_NOT_FOUND: "resource not found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method not allowed",
    status.HTTP_409_CONFLICT: "the request conflicts with the current state",
    status.HTTP_413_CONTENT_TOO_LARGE: "request body too large",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported media type",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation failed",
    status.HTTP_429_TOO_MANY_REQUESTS: "too many requests",
}


def message_for_status(status_code: int) -> str:
    if status_code >= 500:
        return "something went wrong"
    return _MESSAGE_BY_STATUS.get(status_code, "the request could not be completed")


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


class ClientError(ClientMessage, AppError):
    """An AppError whose message is written for clients. A plain AppError keeps its
    message for the log, and its client gets the status's fixed text."""


class ClientHTTPException(ClientMessage, HTTPException):
    """An HTTPException whose detail is written for clients. Any other's detail,
    including the framework's own, is replaced by the status's fixed text."""


class RateLimitedError(ClientError):
    """429 with a Retry-After hint. One message for every limit and lock, so
    the response never reveals which rule fired or whether an account exists."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("too many requests", status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        self.retry_after = max(int(retry_after), 1)


class AnswerWithheldError(ClientError):
    """503 with a Retry-After hint: an AI answer drew on a document the caller
    may not read now, or that's denied, so none of it is returned (M3-D
    provenance check). A retry retrieves afresh, without that document."""

    def __init__(self, retry_after: int = 1) -> None:
        super().__init__(
            "the answer was withheld; try again", status_code=status.HTTP_503_SERVICE_UNAVAILABLE, code="ANSWER_WITHHELD"
        )
        self.retry_after = max(int(retry_after), 1)


class NotFoundError(ClientError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


def public_message(exc: Exception, fallback: str = "the request could not be completed") -> str:
    """Text for a client, from an exception a route expects. Only an exception marked
    as written for clients keeps its message; anything else gets the fallback, because
    its text may quote input or name internals."""
    return str(exc) if isinstance(exc, ClientMessage) else fallback


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
        # The final point of disclosure: unmarked text never leaves, whoever raised it.
        str(exc.detail) if isinstance(exc, ClientMessage) else message_for_status(exc.status_code),
        # Keep WWW-Authenticate (401), Allow (405) and similar headers.
        headers=dict(exc.headers) if exc.headers else None,
    )


_LOCATION_ROOTS = frozenset({"body", "query", "path", "header", "cookie"})


def _safe_location(location: tuple[object, ...], declared: Collection[str]) -> str:
    """A submitted object's own keys appear in a location, and can look like any other
    name. So a name is kept only if the API declares it, and otherwise becomes *."""
    known = _LOCATION_ROOTS | set(declared)
    return ".".join(str(part) if isinstance(part, int) or part in known else "*" for part in location)


def _declared_names(target: Any) -> frozenset[str]:
    """Every property and parameter name in the application's own schema."""
    names: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    names.update(value)
                if key == "parameters" and isinstance(value, list):
                    names.update(p["name"] for p in value if isinstance(p, dict) and "name" in p)
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(target.openapi())
    return frozenset(names)


# Written here, by error type. Pydantic's own text is never passed on: it can change
# between versions and some of it quotes the input. A type not listed gets the default.
_VALIDATION_MESSAGES = {
    "missing": "this field is required",
    "extra_forbidden": "this field is not allowed",
    "json_invalid": "the request body is not valid JSON",
    "string_type": "must be text",
    "string_too_short": "too short",
    "string_too_long": "too long",
    "string_pattern_mismatch": "not in the expected format",
    "int_type": "must be a whole number",
    "int_parsing": "must be a whole number",
    "float_type": "must be a number",
    "float_parsing": "must be a number",
    "bool_type": "must be true or false",
    "bool_parsing": "must be true or false",
    "list_type": "must be a list",
    "dict_type": "must be an object",
    "model_attributes_type": "must be an object",
    "greater_than": "too small",
    "greater_than_equal": "too small",
    "less_than": "too large",
    "less_than_equal": "too large",
    "too_short": "too few items",
    "too_long": "too many items",
    "literal_error": "not an accepted value",
    "enum": "not an accepted value",
    "datetime_type": "must be a date and time",
    "datetime_parsing": "must be a date and time",
    "datetime_from_date_parsing": "must be a date and time",
    "uuid_type": "must be a UUID",
    "uuid_parsing": "must be a UUID",
}
_SAFE_VALIDATION_CODE = re.compile(r"[a-z_]{1,64}")


def _safe_validation_message(error: Any) -> str:
    kind = error["type"]
    if kind in ("value_error", "assertion_error"):
        cause = error.get("ctx", {}).get("error")
        return str(cause) if isinstance(cause, ClientMessage) else "invalid value"
    return _VALIDATION_MESSAGES.get(kind, "invalid value")


def safe_validation_details(errors: Iterable[Any], declared: Collection[str]) -> dict[str, object]:
    """Where and why, never the refused value: it may be a password."""
    return {
        "fields": [
            {
                "field": _safe_location(e["loc"], declared),
                "code": e["type"] if _SAFE_VALIDATION_CODE.fullmatch(e["type"]) else "invalid",
                "message": _safe_validation_message(e),
            }
            for e in errors
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
        details=safe_validation_details(exc.errors(), _declared_names(request.app)),
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
    retry_after = exc.retry_after if isinstance(exc, (RateLimitedError, AnswerWithheldError)) else None
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    # The final point of disclosure: unmarked text never leaves, whoever raised it.
    message = exc.message if isinstance(exc, ClientMessage) else message_for_status(exc.status_code)
    return error_response(request, exc.status_code, exc.code, message, headers=headers)


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

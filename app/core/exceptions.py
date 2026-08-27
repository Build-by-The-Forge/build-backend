import structlog
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.metrics import errors_total

logger = structlog.get_logger(__name__)


class AppError(Exception):
    def __init__(
        self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise TypeError("expected HTTPException")
    request_id = getattr(request.state, "request_id", None)
    errors_total.labels(error_type="HTTPException").inc()
    logger.warning(
        "http_exception",
        request_id=request_id,
        status_code=exc.status_code,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": {},
            "meta": {"error": exc.detail},
            **({"request_id": request_id} if request_id is not None else {}),
        },
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("expected RequestValidationError")
    request_id = getattr(request.state, "request_id", None)
    errors_total.labels(error_type="RequestValidationError").inc()
    logger.warning(
        "request_validation_failed",
        request_id=request_id,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "data": {},
            "meta": {"error": "validation failed", "details": exc.errors()},
            **({"request_id": request_id} if request_id is not None else {}),
        },
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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": {},
            "meta": {"error": exc.message},
            **({"request_id": request_id} if request_id is not None else {}),
        },
    )

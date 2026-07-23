from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.identity import router as identity_router
from app.api.router import router as api_router
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.metrics import metrics_payload, requests_total
from app.core.middleware import RequestContextMiddleware
from app.core.responses import ApiResponse
from app.core.security import SecurityHeadersMiddleware
from app.core.tracing import configure_tracing

configure_logging()
configure_tracing()

app = FastAPI(title="BUILD Backend", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(health_router)
app.include_router(api_router)
app.include_router(identity_router)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(AppError, app_exception_handler)


@app.get("/")
def read_root(request: Request) -> ApiResponse:
    return ApiResponse(
        data={
            "message": "BUILD backend is running",
            "environment": settings.app_environment,
        },
        meta={"environment": settings.app_environment},
        request_id=getattr(request.state, "request_id", None),
    )


@app.get("/metrics")
def metrics() -> str:
    requests_total.inc()
    return metrics_payload().decode("utf-8")

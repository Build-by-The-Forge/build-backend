import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.identity import router as identity_router
from app.api.router import router as api_router
from app.api.tenant_invitations import router as tenant_invitations_router
from app.api.tenant_join import router as tenant_join_router
from app.api.tenant_members import router as tenant_members_router
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.metrics import learning_memory_enabled, metrics_payload, requests_total
from app.core.middleware import RequestContextMiddleware
from app.core.responses import ApiResponse
from app.core.security import SecurityHeadersMiddleware
from app.core.tracing import configure_tracing
from app.db.base import Base
from app.db.session import engine
from app.infrastructure.security.replay_store import RedisReplayStore
from app.infrastructure.security.service_signature import Direction, ServiceKeys
from app.middleware.body_limit import RequestBodyLimitMiddleware, RouteBodyLimit
from app.middleware.service_auth import ServiceAuthMiddleware

# The one route AI-service may call. Only BUILD Service Signature v1 requests
# signed with AI_TO_BACKEND_SECRET reach it (design B.3).
INGESTION_CALLBACK_PATH = "/content/ingestion/callbacks"

configure_logging()
configure_tracing()


def _callback_keys() -> ServiceKeys | None:
    secrets = settings.ai_to_backend_verification_secrets
    if not secrets:
        return None  # development without the secret: callbacks are refused
    return ServiceKeys(current=secrets[0], previous=secrets[1] if len(secrets) > 1 else None)


def _is_callback_path(path: str) -> bool:
    return path == INGESTION_CALLBACK_PATH or path.startswith(INGESTION_CALLBACK_PATH + "/")


logger = logging.getLogger(__name__)


async def initialize_database() -> None:
    if settings.effective_postgres_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    enabled = settings.learning_memory_allowed
    learning_memory_enabled.set(1 if enabled else 0)
    logger.info(f"Learning memory: {'enabled' if enabled else 'disabled by the production gate'}")
    yield


app = FastAPI(
    title="BUILD Backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# Replay protection is shared by every replica, so it lives in Redis only.
app.state.service_replay_store = RedisReplayStore.from_url(
    settings.redis_url, timeout_seconds=settings.service_replay_timeout_seconds
)
app.add_middleware(
    ServiceAuthMiddleware,
    receiver="build-backend",
    direction=Direction.AI_TO_BACKEND,
    keys=_callback_keys(),
    is_protected=_is_callback_path,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-Slug", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
# Outermost: an oversized body is refused before anything else reads it.
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_bytes=settings.max_request_body_bytes,
    # Document uploads and version uploads (P3-1 PR 2, PR 3b) take up to
    # max_upload_bytes; every other
    # route keeps max_request_body_bytes.
    route_limits=[
        RouteBodyLimit("POST", r"/content/sources/[^/]+/assets/upload", settings.max_upload_bytes),
        RouteBodyLimit("POST", r"/content/assets/[^/]+/versions/upload", settings.max_upload_bytes),
    ],
)
app.include_router(health_router)
app.include_router(api_router)
app.include_router(identity_router)
app.include_router(tenant_invitations_router)
app.include_router(tenant_members_router)
app.include_router(tenant_join_router)
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

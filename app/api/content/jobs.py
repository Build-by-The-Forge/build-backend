from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.content.callback_schemas import (
    AICallbackRequest,
    AICallbackResponse,
)
from app.api.content.job_schemas import (
    IngestionJobCreateRequest,
    IngestionJobReprocessRequest,
    IngestionJobResponse,
    IngestionJobRetryRequest,
)
from app.application.content.job_handlers import ReconcileMismatchError
from app.application.content.job_service import ContentIngestionJobService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.content.enums import IngestionStatus
from app.domain.content.job import (
    CallbackOutcome,
    InvalidJobTransition,
    InvalidStageEvidence,
    RetryNotDue,
)
from app.infrastructure.security.service_context import ACTOR_SYSTEM
from app.infrastructure.security.service_signature import VerifiedServiceRequest
from app.infrastructure.content.ai_gateway import AIServiceGatewayError
from app.middleware.service_auth import STATE_KEY as SERVICE_AUTH_STATE_KEY

router = APIRouter(prefix="", tags=["content-ingestion-jobs"])
service = build_container().get(ContentIngestionJobService)


@router.post(
    "/assets/{asset_id}/jobs",
    status_code=status.HTTP_201_CREATED,
    response_model=IngestionJobResponse,
)
async def trigger_ingestion_job(
    asset_id: str,
    payload: IngestionJobCreateRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.create_job(
            asset_id=asset_id,
            tenant_id=context.tenant_id,
            created_by=context.user_id,
            max_attempts=payload.max_attempts,
            correlation_id=payload.correlation_id,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "does not exist" in msg else status.HTTP_400_BAD_REQUEST
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "INGESTION_TRIGGER_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"data": resp_data})


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobResponse,
)
async def get_ingestion_job(
    job_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_READ)),
) -> JSONResponse:
    job = await service.get_job(job_id=job_id, tenant_id=context.tenant_id)
    if job is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"ContentIngestionJob with id '{job_id}' not found",
                }
            },
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.get(
    "/assets/{asset_id}/jobs/latest",
    response_model=IngestionJobResponse,
)
async def get_latest_job_for_asset(
    asset_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_READ)),
) -> JSONResponse:
    job = await service.get_latest_job_for_asset(asset_id=asset_id, tenant_id=context.tenant_id)
    if job is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"No ingestion job found for asset '{asset_id}'",
                }
            },
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.get("/assets/{asset_id}/jobs")
async def list_jobs_for_asset(
    asset_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_READ)),
) -> JSONResponse:
    jobs, total = await service.list_jobs(
        tenant_id=context.tenant_id,
        asset_id=asset_id,
        limit=limit,
        offset=offset,
    )
    items = [IngestionJobResponse.from_domain(j).model_dump(mode="json") for j in jobs]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": items,
            "meta": {"total": total, "limit": limit, "offset": offset},
        },
    )


@router.get("/jobs")
async def list_ingestion_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_READ)),
) -> JSONResponse:
    st = IngestionStatus(status_filter) if status_filter else None
    jobs, total = await service.list_jobs(
        tenant_id=context.tenant_id,
        source_id=source_id,
        status=st,
        limit=limit,
        offset=offset,
    )
    items = [IngestionJobResponse.from_domain(j).model_dump(mode="json") for j in jobs]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": items,
            "meta": {"total": total, "limit": limit, "offset": offset},
        },
    )


@router.post(
    "/jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
)
async def retry_job(
    job_id: str,
    payload: IngestionJobRetryRequest,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.retry_job(job_id=job_id, tenant_id=context.tenant_id, delay_seconds=payload.delay_seconds)
    except InvalidJobTransition as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "TRANSITION_NOT_ALLOWED", "message": str(exc)}},
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "does not exist" in msg else status.HTTP_400_BAD_REQUEST
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "RETRY_JOB_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.post(
    "/assets/{asset_id}/reprocess",
    status_code=status.HTTP_201_CREATED,
    response_model=IngestionJobResponse,
)
async def reprocess_asset(
    asset_id: str,
    payload: IngestionJobReprocessRequest,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.reprocess_asset(
            asset_id=asset_id,
            tenant_id=context.tenant_id,
            created_by=context.user_id,
            correlation_id=payload.correlation_id,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "does not exist" in msg else status.HTTP_400_BAD_REQUEST
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "REPROCESS_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"data": resp_data})


@router.post(
    "/jobs/{job_id}/dispatch",
    response_model=IngestionJobResponse,
)
async def dispatch_ingestion_job(
    job_id: str,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    # No request body: where AI-service reports back is never chosen by the
    # caller. The signed context carries this caller and the one permission
    # checked here (design B.2, decision E.6).
    try:
        job = await service.dispatch_job(
            job_id=job_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            membership_id=context.membership_id,
            role=context.role,
            permission=Permission.CONTENT_JOB_MANAGE.value,
        )
    except RetryNotDue as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "RETRY_NOT_DUE", "message": str(exc)}},
        )
    except InvalidJobTransition as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "TRANSITION_NOT_ALLOWED", "message": str(exc)}},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "DISPATCH_FAILED", "message": str(exc)}},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": getattr(exc, "error_code", "AI_GATEWAY_ERROR"),
                    "message": str(exc),
                }
            },
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    if job.status == IngestionStatus.FAILED:
        # The dispatch failed and the job's failed state was saved; report it.
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": job.error_code or "AI_DISPATCH_FAILED",
                    "message": job.error_message or "AI-service dispatch failed",
                },
                "data": resp_data,
            },
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.post(
    "/jobs/{job_id}/reconcile",
    response_model=IngestionJobResponse,
)
async def reconcile_ingestion_job(
    job_id: str,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    """Apply AI-service's account of the job's active task (design B.3).

    The recorded events go through the same rules as delivered callbacks;
    ``meta.reconciled`` lists each event's outcome.
    """
    try:
        result = await service.reconcile_job(job_id=job_id, tenant_id=context.tenant_id)
    except InvalidJobTransition as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "TRANSITION_NOT_ALLOWED", "message": str(exc)}},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "JOB_NOT_FOUND", "message": str(exc)}},
        )
    except ReconcileMismatchError as exc:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": {"code": "AI_STATUS_MISMATCH", "message": str(exc)}},
        )
    except AIServiceGatewayError as exc:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": {"code": exc.error_code, "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(result.job).model_dump(mode="json")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": resp_data,
            "meta": {"reconciled": [{"event_id": event_id, "outcome": outcome} for event_id, outcome in result.outcomes]},
        },
    )


@router.post(
    "/ingestion/callbacks",
    response_model=AICallbackResponse,
)
async def handle_ai_callback(request: Request) -> JSONResponse:
    """Processing events from AI-service (design B.3).

    ServiceAuthMiddleware has already verified the BUILD Service Signature v1
    request (AI_TO_BACKEND_SECRET, sender ai-service, replay, 1 MiB body)
    before this runs; there is no other way in.
    """
    verified = getattr(request.state, SERVICE_AUTH_STATE_KEY, None)
    if not isinstance(verified, VerifiedServiceRequest):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "invalid service authentication"},
        )
    # A callback is a system operation: it carries no user and grants
    # nothing. A user context here is a misuse of the AI-to-backend secret.
    context = verified.context
    if context.actor != ACTOR_SYSTEM:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "callbacks require a system context"},
        )

    try:
        payload = AICallbackRequest.model_validate_json(await request.body())
    except ValidationError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "INVALID_PAYLOAD",
                    "message": "callback body failed validation",
                    "details": exc.errors(include_url=False, include_input=False, include_context=False),
                }
            },
        )

    try:
        job, outcome = await service.handle_callback(
            job_id=payload.job_id,
            tenant_id=context.tenant_id,
            event_id=payload.event_id,
            event_type=payload.event_type,
            stage=payload.stage,
            external_task_id=payload.external_task_id,
            run_number=payload.run_number,
            attempt_count=payload.attempt_count,
            metrics=payload.metrics,
            error_code=payload.error_code,
            error_message=payload.error_message,
            is_retryable=payload.is_retryable,
            details=payload.details,
        )
    except InvalidStageEvidence as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"error": {"code": "INVALID_STAGE_EVIDENCE", "message": str(exc)}},
        )

    if job is None or outcome is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "JOB_NOT_FOUND", "message": "Job not found"}},
        )

    if outcome is CallbackOutcome.CONFLICT:
        # The event id was already used for different content.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "EVENT_CONFLICT",
                    "message": "event_id was already recorded with different content",
                },
                "data": {"job_id": job.id, "outcome": outcome.value},
            },
        )

    if outcome is CallbackOutcome.NOT_ALLOWED:
        # Not consumed: the job is not in a state this event can move it from.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "TRANSITION_NOT_ALLOWED",
                    "message": f"event not allowed while the job is {job.status.value}",
                },
                "data": {"job_id": job.id, "outcome": outcome.value},
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {
                "status": "accepted",
                "job_id": job.id,
                "outcome": outcome.value,
                "already_processed": outcome is not CallbackOutcome.APPLIED,
            }
        },
    )

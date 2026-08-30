from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.content.callback_schemas import (
    AICallbackRequest,
    AICallbackResponse,
    AIDispatchRequest,
)
from app.api.content.job_schemas import (
    IngestionJobCompleteRequest,
    IngestionJobCreateRequest,
    IngestionJobFailRequest,
    IngestionJobProgressRequest,
    IngestionJobReprocessRequest,
    IngestionJobResponse,
    IngestionJobRetryRequest,
)
from app.application.content.job_service import ContentIngestionJobService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.config import settings
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.content.enums import IngestionStatus
from app.infrastructure.content.ai_gateway import verify_webhook_signature

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
            created_by=context.user_id,
            max_attempts=payload.max_attempts,
            correlation_id=payload.correlation_id,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {"code": "INGESTION_TRIGGER_FAILED", "message": str(exc)}
            },
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"data": resp_data}
    )


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
    job = await service.get_latest_job_for_asset(
        asset_id=asset_id, tenant_id=context.tenant_id
    )
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
    "/jobs/{job_id}/start",
    response_model=IngestionJobResponse,
)
async def start_job(
    job_id: str,
    stage: str = Query(default="parsing"),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.start_job(job_id=job_id, stage=stage)
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "START_JOB_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.post(
    "/jobs/{job_id}/progress",
    response_model=IngestionJobResponse,
)
async def progress_job(
    job_id: str,
    payload: IngestionJobProgressRequest,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.progress_job(
            job_id=job_id,
            target_stage=payload.target_stage,
            metrics=payload.metrics,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "PROGRESS_JOB_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.post(
    "/jobs/{job_id}/complete",
    response_model=IngestionJobResponse,
)
async def complete_job(
    job_id: str,
    payload: IngestionJobCompleteRequest,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.complete_job(job_id=job_id, metrics=payload.metrics)
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "COMPLETE_JOB_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.post(
    "/jobs/{job_id}/fail",
    response_model=IngestionJobResponse,
)
async def fail_job(
    job_id: str,
    payload: IngestionJobFailRequest,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    try:
        job = await service.fail_job(
            job_id=job_id,
            error_code=payload.error_code,
            error_message=payload.error_message,
            is_retryable=payload.is_retryable,
            details=payload.details,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "FAIL_JOB_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


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
        job = await service.retry_job(
            job_id=job_id, delay_seconds=payload.delay_seconds
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
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
            created_by=context.user_id,
            correlation_id=payload.correlation_id,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "REPROCESS_FAILED", "message": str(exc)}},
        )

    resp_data = IngestionJobResponse.from_domain(job).model_dump(mode="json")
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"data": resp_data}
    )


@router.post(
    "/jobs/{job_id}/dispatch",
    response_model=IngestionJobResponse,
)
async def dispatch_ingestion_job(
    job_id: str,
    payload: AIDispatchRequest | None = None,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_JOB_MANAGE)),
) -> JSONResponse:
    callback_url = payload.callback_url if payload else None
    try:
        job = await service.dispatch_job(job_id=job_id, callback_url=callback_url)
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
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.post(
    "/ingestion/callbacks",
    response_model=AICallbackResponse,
)
async def handle_ai_callback(
    request: Request,
    x_build_signature: str | None = Header(default=None, alias="X-Build-Signature"),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    body_bytes = await request.body()

    # Authenticate webhook signature or bearer token
    is_valid_hmac = verify_webhook_signature(
        payload_bytes=body_bytes,
        signature_header=x_build_signature,
        secret=settings.ai_service_webhook_secret,
    )
    is_valid_bearer = (
        authorization is not None
        and authorization.strip() == f"Bearer {settings.ai_service_api_key}"
    )

    if not is_valid_hmac and not is_valid_bearer:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "INVALID_CALLBACK_AUTH",
                    "message": "Missing or invalid HMAC signature / API Key",
                }
            },
        )

    try:
        payload = AICallbackRequest.model_validate_json(body_bytes)
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "INVALID_PAYLOAD", "message": str(exc)}},
        )

    job, already_processed = await service.handle_callback(
        job_id=payload.job_id,
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

    if job is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job '{payload.job_id}' not found",
                }
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {
                "status": "accepted",
                "job_id": job.id,
                "already_processed": already_processed,
            }
        },
    )

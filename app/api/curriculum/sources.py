from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.curriculum.schemas import (
    CreateCurriculumSourceRequest,
    CurriculumSnapshotResponse,
    CurriculumSourceResponse,
    CurriculumSyncTriggerResponse,
)
from app.application.curriculum.curriculum_source_service import (
    CurriculumSourceService,
)
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.curriculum.source import CurriculumSnapshot, CurriculumSource

router = APIRouter(prefix="/curriculum", tags=["curriculum"])
service = build_container().get(CurriculumSourceService)


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: CreateCurriculumSourceRequest,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_MANAGE)
    ),
) -> JSONResponse:
    try:
        source = await service.register_source(
            code=payload.code,
            name=payload.name,
            base_url=payload.base_url,
            source_type=payload.source_type,
            sync_frequency_days=payload.sync_frequency_days,
            parser_version=payload.parser_version,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": _source_payload(source),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/sources", status_code=status.HTTP_200_OK)
async def list_sources(
    request: Request,
    status_filter: str | None = None,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_READ)
    ),
) -> JSONResponse:
    sources = await service.list_sources(status=status_filter)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_source_payload(s) for s in sources],
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/sources/{source_id}", status_code=status.HTTP_200_OK)
async def get_source(
    source_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_READ)
    ),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="curriculum source not found"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _source_payload(source),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/sources/{source_id}/snapshots", status_code=status.HTTP_200_OK)
async def list_snapshots(
    source_id: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_READ)
    ),
) -> JSONResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="offset must be greater than or equal to 0",
        )

    res = await service.list_snapshots(source_id=source_id, limit=limit, offset=offset)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="curriculum source not found"
        )

    snapshots, total = res
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_snapshot_payload(s) for s in snapshots],
            "meta": {"total": total, "limit": limit, "offset": offset},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/sources/{source_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    source_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_MANAGE)
    ),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="curriculum source not found"
        )

    job_id = f"job-sync-{uuid4()}"
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "success": True,
            "data": CurriculumSyncTriggerResponse(
                job_id=job_id,
                status="queued",
            ).model_dump(),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _source_payload(source: CurriculumSource) -> dict[str, object]:
    return CurriculumSourceResponse(
        id=source.id,
        code=source.code,
        name=source.name,
        base_url=source.base_url,
        source_type=source.source_type,
        status=source.status.value,
        sync_frequency_days=source.sync_frequency_days,
        parser_version=source.parser_version,
        created_at=source.created_at.isoformat(),
        updated_at=source.updated_at.isoformat(),
    ).model_dump()


def _snapshot_payload(snapshot: CurriculumSnapshot) -> dict[str, object]:
    return CurriculumSnapshotResponse(
        id=snapshot.id,
        source_id=snapshot.source_id,
        source_url=snapshot.source_url,
        retrieved_at=snapshot.retrieved_at.isoformat(),
        content_sha256=snapshot.content_sha256,
        parser_version=snapshot.parser_version,
        status=snapshot.status.value,
        created_at=snapshot.created_at.isoformat(),
    ).model_dump()

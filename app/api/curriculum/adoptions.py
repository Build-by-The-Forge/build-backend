from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.curriculum.adoption_schemas import (
    AdoptBenchmarkRequest,
    CreateOverrideRequest,
    CurriculumOverrideResponse,
    InstitutionalAdoptionResponse,
)
from app.application.curriculum.institutional_adoption_service import (
    InstitutionalAdoptionService,
)
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.curriculum.adoption import (
    CurriculumOverride,
    InstitutionalAdoption,
)

router = APIRouter(prefix="/curriculum/adoptions", tags=["curriculum-adoptions"])
service = build_container().get(InstitutionalAdoptionService)


@router.post("", status_code=status.HTTP_201_CREATED)
async def adopt_benchmark(
    payload: AdoptBenchmarkRequest,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_MANAGE)
    ),
) -> JSONResponse:
    try:
        adoption = await service.adopt_benchmark(
            tenant_id=context.tenant_id,
            programme_id=payload.programme_id,
            benchmark_curriculum_id=payload.benchmark_curriculum_id,
            actor_id=context.tenant_id,
            actor_email=f"{context.tenant_id}@build.internal",
            academic_session_id=payload.academic_session_id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": _adoption_payload(adoption),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("", status_code=status.HTTP_200_OK)
async def list_adoptions(
    request: Request,
    programme_id: str | None = None,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_READ)
    ),
) -> JSONResponse:
    adoptions = await service.list_adoptions(
        tenant_id=context.tenant_id,
        programme_id=programme_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_adoption_payload(a) for a in adoptions],
            "meta": {"total": len(adoptions)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{adoption_id}", status_code=status.HTTP_200_OK)
async def get_adoption(
    adoption_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_READ)
    ),
) -> JSONResponse:
    try:
        adoption, overrides = await service.get_adoption_detail(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "adoption": _adoption_payload(adoption),
                "overrides": [_override_payload(o) for o in overrides],
            },
            "meta": {"overrides_count": len(overrides)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{adoption_id}/activate", status_code=status.HTTP_200_OK)
async def activate_adoption(
    adoption_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_MANAGE)
    ),
) -> JSONResponse:
    try:
        adoption, superseded = await service.activate_adoption(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
            actor_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "activated": _adoption_payload(adoption),
                "superseded": (
                    _adoption_payload(superseded) if superseded is not None else None
                ),
            },
            "meta": {
                "superseded_adoption_id": (
                    superseded.id if superseded is not None else None
                )
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{adoption_id}/overrides", status_code=status.HTTP_201_CREATED)
async def add_override(
    adoption_id: str,
    payload: CreateOverrideRequest,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_MANAGE)
    ),
) -> JSONResponse:
    try:
        override = await service.add_override(
            adoption_id=adoption_id,
            tenant_id=context.tenant_id,
            override_type=payload.override_type,
            reason=payload.reason,
            actor_id=context.tenant_id,
            actor_email=f"{context.tenant_id}@build.internal",
            target_course_code=payload.target_course_code,
            target_topic_id=payload.target_topic_id,
            target_outcome_id=payload.target_outcome_id,
            field_overrides=payload.field_overrides,
            custom_payload=payload.custom_payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": _override_payload(override),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.delete("/{adoption_id}/overrides/{override_id}", status_code=status.HTTP_200_OK)
async def remove_override(
    adoption_id: str,
    override_id: str,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CURRICULUM_SOURCE_MANAGE)
    ),
) -> JSONResponse:
    try:
        deleted = await service.remove_override(
            adoption_id=adoption_id,
            override_id=override_id,
            tenant_id=context.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="override not found or already deleted",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"deleted": True, "override_id": override_id},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _adoption_payload(adoption: InstitutionalAdoption) -> dict[str, object]:
    return InstitutionalAdoptionResponse(
        id=adoption.id,
        tenant_id=adoption.tenant_id,
        programme_id=adoption.programme_id,
        benchmark_curriculum_id=adoption.benchmark_curriculum_id,
        benchmark_version=adoption.benchmark_version,
        benchmark_fingerprint=adoption.benchmark_fingerprint,
        academic_session_id=adoption.academic_session_id,
        status=adoption.status.value,
        notes=adoption.notes,
        adopted_by=adoption.adopted_by,
        adopted_by_email=adoption.adopted_by_email,
        created_at=adoption.created_at.isoformat(),
        updated_at=adoption.updated_at.isoformat(),
    ).model_dump()


def _override_payload(override: CurriculumOverride) -> dict[str, object]:
    return CurriculumOverrideResponse(
        id=override.id,
        adoption_id=override.adoption_id,
        override_type=override.override_type.value,
        target_course_code=override.target_course_code,
        target_topic_id=override.target_topic_id,
        target_outcome_id=override.target_outcome_id,
        field_overrides=override.field_overrides,
        custom_payload=override.custom_payload,
        reason=override.reason,
        created_by=override.created_by,
        created_by_email=override.created_by_email,
        created_at=override.created_at.isoformat(),
    ).model_dump()

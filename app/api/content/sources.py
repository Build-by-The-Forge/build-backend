from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.content.schemas import (
    ContentSourceCreateRequest,
    ContentSourceReasonRequest,
    ContentSourceResponse,
    ContentSourceUpdateRequest,
)
from app.application.content.source_service import ContentSourceService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.content.enums import VisibilityScope
from app.domain.content.source import ContentSource

router = APIRouter(prefix="/sources", tags=["content-sources"])
service = build_container().get(ContentSourceService)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: ContentSourceCreateRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_MANAGE)),
) -> JSONResponse:
    # If platform scope requested, ensure caller is platform admin (tenant_id is None or system admin)
    tenant_id = None if payload.visibility == VisibilityScope.PLATFORM.value else context.tenant_id

    try:
        source = await service.register_source(
            code=payload.code,
            name=payload.name,
            source_type=payload.source_type,
            authority_level=payload.authority_level,
            visibility=payload.visibility,
            created_by=context.user_id,
            created_by_email=f"{context.user_id}@build.internal",
            tenant_id=tenant_id,
            faculty_id=payload.faculty_id,
            department_id=payload.department_id,
            programme_id=payload.programme_id,
            description=payload.description,
            author_name=payload.author_name,
            publisher=payload.publisher,
            isbn_or_doi=payload.isbn_or_doi,
            source_url=payload.source_url,
            trust_policy=payload.trust_policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": _source_payload(source),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("", status_code=status.HTTP_200_OK)
async def list_sources(
    request: Request,
    source_type: str | None = None,
    authority_level: str | None = None,
    status_filter: str | None = None,
    include_platform: bool = True,
    limit: int = 50,
    offset: int = 0,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_READ)),
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

    sources, total = await service.list_sources(
        tenant_id=context.tenant_id,
        source_type=source_type,
        authority_level=authority_level,
        status=status_filter,
        include_platform=include_platform,
        limit=limit,
        offset=offset,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [_source_payload(s) for s in sources],
            "meta": {"total": total, "limit": limit, "offset": offset},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/{source_id}", status_code=status.HTTP_200_OK)
async def get_source(
    source_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_READ)),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content source not found")

    # Check accessibility within caller's tenant
    if not source.is_accessible_by(tenant_id=context.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access denied to content source outside tenant scope",
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


@router.patch("/{source_id}", status_code=status.HTTP_200_OK)
async def update_source(
    source_id: str,
    payload: ContentSourceUpdateRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_MANAGE)),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content source not found")

    if not source.is_accessible_by(tenant_id=context.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot update content source outside tenant scope",
        )

    try:
        updated = await service.update_source(
            source_id=source_id,
            name=payload.name,
            description=payload.description,
            author_name=payload.author_name,
            publisher=payload.publisher,
            isbn_or_doi=payload.isbn_or_doi,
            source_url=payload.source_url,
            trust_policy=payload.trust_policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _source_payload(updated),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{source_id}/deprecate", status_code=status.HTTP_200_OK)
async def deprecate_source(
    source_id: str,
    payload: ContentSourceReasonRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_MANAGE)),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content source not found")

    if not source.is_accessible_by(tenant_id=context.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot manage content source outside tenant scope",
        )

    try:
        updated = await service.deprecate_source(source_id=source_id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _source_payload(updated),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{source_id}/revoke", status_code=status.HTTP_200_OK)
async def revoke_source(
    source_id: str,
    payload: ContentSourceReasonRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_MANAGE)),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content source not found")

    if not source.is_accessible_by(tenant_id=context.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot manage content source outside tenant scope",
        )

    try:
        updated = await service.revoke_source(source_id=source_id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _source_payload(updated),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/{source_id}/activate", status_code=status.HTTP_200_OK)
async def activate_source(
    source_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_SOURCE_MANAGE)),
) -> JSONResponse:
    source = await service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="content source not found")

    if not source.is_accessible_by(tenant_id=context.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot manage content source outside tenant scope",
        )

    updated = await service.activate_source(source_id=source_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": _source_payload(updated),
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _source_payload(source: ContentSource) -> dict[str, object]:
    return ContentSourceResponse(
        id=source.id,
        code=source.code,
        name=source.name,
        source_type=source.source_type.value,
        authority_level=source.authority_level.value,
        visibility=source.visibility.value,
        status=source.status.value,
        tenant_id=source.tenant_id,
        faculty_id=source.faculty_id,
        department_id=source.department_id,
        programme_id=source.programme_id,
        description=source.description,
        author_name=source.author_name,
        publisher=source.publisher,
        isbn_or_doi=source.isbn_or_doi,
        source_url=source.source_url,
        trust_policy=source.trust_policy,
        created_by=source.created_by,
        created_by_email=source.created_by_email,
        created_at=source.created_at.isoformat(),
        updated_at=source.updated_at.isoformat(),
    ).model_dump()

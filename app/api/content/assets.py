from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.content.asset_schemas import (
    ContentAssetRegisterRequest,
    ContentAssetResponse,
    ContentAssetRevokeRequest,
    ContentAssetVersionRequest,
)
from app.application.content.asset_service import ContentAssetService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.content.enums import AssetStatus, IngestionStatus

router = APIRouter(prefix="", tags=["content-assets"])
service = build_container().get(ContentAssetService)


@router.post(
    "/sources/{source_id}/assets",
    status_code=status.HTTP_201_CREATED,
    response_model=ContentAssetResponse,
)
async def register_asset(
    source_id: str,
    payload: ContentAssetRegisterRequest,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CONTENT_ASSET_UPLOAD)
    ),
) -> JSONResponse:
    try:
        asset, is_deduplicated = await service.register_asset(
            source_id=source_id,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            file_size_bytes=payload.file_size_bytes,
            content_sha256=payload.content_sha256,
            storage_uri=payload.storage_uri,
            created_by=context.user_id,
            created_by_email=f"{context.user_id}@build.internal",
            tenant_id=context.tenant_id,
            metadata=payload.metadata,
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
            content={"error": {"code": "INVALID_CONTENT_ASSET", "message": str(exc)}},
        )

    resp_data = ContentAssetResponse.from_domain(
        asset, is_deduplicated=is_deduplicated
    ).model_dump(mode="json")
    status_code = status.HTTP_200_OK if is_deduplicated else status.HTTP_201_CREATED
    return JSONResponse(status_code=status_code, content={"data": resp_data})


@router.get(
    "/assets/{asset_id}",
    response_model=ContentAssetResponse,
)
async def get_asset(
    asset_id: str,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_READ)),
) -> JSONResponse:
    asset = await service.get_asset(asset_id=asset_id, tenant_id=context.tenant_id)
    if asset is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "ASSET_NOT_FOUND",
                    "message": f"ContentAsset with id '{asset_id}' not found",
                }
            },
        )

    resp_data = ContentAssetResponse.from_domain(asset).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})


@router.get("/sources/{source_id}/assets")
async def list_source_assets(
    source_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_READ)),
) -> JSONResponse:
    assets, total = await service.list_assets(
        tenant_id=context.tenant_id,
        source_id=source_id,
        limit=limit,
        offset=offset,
    )
    items = [
        ContentAssetResponse.from_domain(a).model_dump(mode="json") for a in assets
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": items, "meta": {"total": total, "limit": limit, "offset": offset}},
    )


@router.get("/assets")
async def list_all_assets(
    status_filter: str | None = Query(default=None, alias="status"),
    ingestion_filter: str | None = Query(default=None, alias="ingestion_status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_READ)),
) -> JSONResponse:
    st = AssetStatus(status_filter) if status_filter else None
    ing_st = IngestionStatus(ingestion_filter) if ingestion_filter else None

    assets, total = await service.list_assets(
        tenant_id=context.tenant_id,
        status=st,
        ingestion_status=ing_st,
        limit=limit,
        offset=offset,
    )
    items = [
        ContentAssetResponse.from_domain(a).model_dump(mode="json") for a in assets
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": items, "meta": {"total": total, "limit": limit, "offset": offset}},
    )


@router.post(
    "/assets/{asset_id}/version",
    status_code=status.HTTP_201_CREATED,
    response_model=ContentAssetResponse,
)
async def create_asset_version(
    asset_id: str,
    payload: ContentAssetVersionRequest,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CONTENT_ASSET_UPLOAD)
    ),
) -> JSONResponse:
    try:
        new_asset = await service.create_version(
            parent_asset_id=asset_id,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            file_size_bytes=payload.file_size_bytes,
            content_sha256=payload.content_sha256,
            storage_uri=payload.storage_uri,
            created_by=context.user_id,
            created_by_email=f"{context.user_id}@build.internal",
            metadata=payload.metadata,
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
            content={"error": {"code": "INVALID_ASSET_VERSION", "message": str(exc)}},
        )

    resp_data = ContentAssetResponse.from_domain(new_asset).model_dump(mode="json")
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"data": resp_data}
    )


@router.post(
    "/assets/{asset_id}/revoke",
    response_model=ContentAssetResponse,
)
async def revoke_asset(
    asset_id: str,
    payload: ContentAssetRevokeRequest,
    request: Request,
    context: TenantContext = Depends(
        require_permission(Permission.CONTENT_ASSET_UPLOAD)
    ),
) -> JSONResponse:
    try:
        revoked = await service.revoke_asset(
            asset_id=asset_id,
            reason=payload.reason,
            revoked_by=context.user_id,
            tenant_id=context.tenant_id,
        )
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else (
                status.HTTP_403_FORBIDDEN
                if "permission denied" in msg
                else status.HTTP_400_BAD_REQUEST
            )
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "REVOCATION_FAILED", "message": str(exc)}},
        )

    resp_data = ContentAssetResponse.from_domain(revoked).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.content.asset_schemas import (
    ContentAssetRegisterRequest,
    ContentAssetResponse,
    ContentAssetRevokeRequest,
    ContentAssetVersionRequest,
)
from app.api.content.upload_body import received_upload
from app.application.content.access import ContentAccessError
from app.application.content.asset_service import ContentAssetService
from app.application.content.upload import (
    ContentAssetUploadService,
    DuplicateContentError,
    UploadedBody,
    UploadError,
    UploadResult,
)
from app.bootstrap.container import build_container
from app.core.authorization import Permission, authorization
from app.core.config import settings
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext
from app.domain.content.enums import AssetStatus, IngestionStatus

router = APIRouter(prefix="", tags=["content-assets"])
service = build_container().get(ContentAssetService)
upload_service = build_container().get(ContentAssetUploadService)


def _access_refused(exc: ContentAccessError) -> JSONResponse:
    """A refused write, by class: 404 for content outside the caller's
    tenant, 403 for platform content (app/application/content/access.py)."""
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": str(exc)}})


@router.post(
    "/sources/{source_id}/assets",
    status_code=status.HTTP_201_CREATED,
    response_model=ContentAssetResponse,
)
async def register_asset(
    source_id: str,
    payload: ContentAssetRegisterRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_UPLOAD)),
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
    except ContentAccessError as exc:
        return _access_refused(exc)
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "does not exist" in msg else status.HTTP_400_BAD_REQUEST
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "INVALID_CONTENT_ASSET", "message": str(exc)}},
        )

    resp_data = ContentAssetResponse.from_domain(asset, is_deduplicated=is_deduplicated).model_dump(mode="json")
    status_code = status.HTTP_200_OK if is_deduplicated else status.HTTP_201_CREATED
    return JSONResponse(status_code=status_code, content={"data": resp_data})


@router.post(
    "/sources/{source_id}/assets/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=ContentAssetResponse,
)
async def upload_asset(
    source_id: str,
    request: Request,
    file_name: str | None = Query(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_UPLOAD)),
) -> JSONResponse:
    """Upload a document as the raw request body (docs/p3-1-pr2-upload-design.md).

    ``file_name`` (percent-encoded query parameter) is a display name only.
    Size, SHA-256 and type come from the bytes; the Content-Type header
    decides nothing. ``Idempotency-Key`` is required: the same key and bytes
    return the original asset (200).
    """
    return await _receive_upload(
        request,
        context,
        lambda body: upload_service.upload(
            source_id=source_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            user_email=f"{context.user_id}@build.internal",
            file_name=file_name,
            idempotency_key=idempotency_key,
            body=body,
            correlation_id=getattr(request.state, "request_id", None),
        ),
    )


@router.post(
    "/assets/{asset_id}/versions/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=ContentAssetResponse,
)
async def upload_asset_version(
    asset_id: str,
    request: Request,
    file_name: str | None = Query(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_UPLOAD)),
) -> JSONResponse:
    """A new version of an asset from uploaded bytes (P3-1 PR 3b, design
    section 9). The asset must be the caller's tenant's current version; it
    stays current until the new version is recorded. A retry with the same
    ``Idempotency-Key`` and bytes returns the same version (200) and never
    supersedes twice."""
    return await _receive_upload(
        request,
        context,
        lambda body: upload_service.upload_version(
            parent_asset_id=asset_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            user_email=f"{context.user_id}@build.internal",
            file_name=file_name,
            idempotency_key=idempotency_key,
            body=body,
            correlation_id=getattr(request.state, "request_id", None),
        ),
    )


async def _receive_upload(
    request: Request, context: TenantContext, store: Callable[[UploadedBody], Awaitable[UploadResult]]
) -> JSONResponse:
    """Stream the body, run ``store`` on it, and answer as the upload
    contract says: 201 created, 200 replayed, typed errors by class."""
    try:
        async with received_upload(
            request,
            max_bytes=settings.max_upload_bytes,
            timeout_seconds=settings.upload_read_timeout_seconds,
        ) as body:
            result = await store(body)
    except ContentAccessError as exc:
        return _access_refused(exc)
    except UploadError as exc:
        error: dict[str, object] = {"code": exc.code, "message": str(exc)}
        # The existing asset is named only to a caller who may read assets.
        if isinstance(exc, DuplicateContentError) and authorization.can(context, Permission.CONTENT_ASSET_READ):
            error["existing_asset_id"] = exc.existing_asset_id
        headers = {"Retry-After": "5"} if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE else None
        return JSONResponse(status_code=exc.status_code, content={"error": error}, headers=headers)

    data = ContentAssetResponse.from_domain(result.asset).model_dump(mode="json")
    status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return JSONResponse(status_code=status_code, content={"data": data})


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
    items = [ContentAssetResponse.from_domain(a).model_dump(mode="json") for a in assets]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": items,
            "meta": {"total": total, "limit": limit, "offset": offset},
        },
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
    items = [ContentAssetResponse.from_domain(a).model_dump(mode="json") for a in assets]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": items,
            "meta": {"total": total, "limit": limit, "offset": offset},
        },
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
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_UPLOAD)),
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
            tenant_id=context.tenant_id,
        )
    except ContentAccessError as exc:
        return _access_refused(exc)
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "does not exist" in msg else status.HTTP_400_BAD_REQUEST
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "INVALID_ASSET_VERSION", "message": str(exc)}},
        )

    resp_data = ContentAssetResponse.from_domain(new_asset).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"data": resp_data})


@router.post(
    "/assets/{asset_id}/revoke",
    response_model=ContentAssetResponse,
)
async def revoke_asset(
    asset_id: str,
    payload: ContentAssetRevokeRequest,
    request: Request,
    context: TenantContext = Depends(require_permission(Permission.CONTENT_ASSET_UPLOAD)),
) -> JSONResponse:
    try:
        revoked = await service.revoke_asset(
            asset_id=asset_id,
            reason=payload.reason,
            revoked_by=context.user_id,
            tenant_id=context.tenant_id,
        )
    except ContentAccessError as exc:
        return _access_refused(exc)
    except ValueError as exc:
        msg = str(exc).lower()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "does not exist" in msg
            else (status.HTTP_403_FORBIDDEN if "permission denied" in msg else status.HTTP_400_BAD_REQUEST)
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "REVOCATION_FAILED", "message": str(exc)}},
        )

    resp_data = ContentAssetResponse.from_domain(revoked).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": resp_data})

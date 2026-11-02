"""Faculties, departments and programmes, for a student choosing where they belong."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.catalogue.courses import service
from app.api.pagination import Page, PageRequest
from app.core.authorization import Permission
from app.core.dependencies import require_permission
from app.core.tenant_context import TenantContext

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


def _page(request: Request, page: PageRequest, entries: list[Any], total: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": [asdict(entry) for entry in entries],
            "error": None,
            "meta": {"request_id": getattr(request.state, "request_id", None), "pagination": page.meta(total)},
        },
    )


@router.get("/faculties", status_code=status.HTTP_200_OK)
async def list_faculties(
    request: Request,
    page: Page,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    entries, total = await service.list_faculties(context.tenant_id, page.limit, page.offset)
    return _page(request, page, entries, total)


@router.get("/departments", status_code=status.HTTP_200_OK)
async def list_departments(
    request: Request,
    page: Page,
    faculty_id: str | None = None,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    entries, total = await service.list_departments(context.tenant_id, faculty_id, page.limit, page.offset)
    return _page(request, page, entries, total)


@router.get("/programmes", status_code=status.HTTP_200_OK)
async def list_programmes(
    request: Request,
    page: Page,
    department_id: str | None = None,
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_READ)),
) -> JSONResponse:
    entries, total = await service.list_programmes(context.tenant_id, department_id, page.limit, page.offset)
    return _page(request, page, entries, total)

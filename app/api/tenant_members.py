from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.application.tenant.membership_service import TenantMembershipService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import require_tenant_permission
from app.core.exceptions import AppError
from app.core.tenant_context import TenantContext
from app.domain.tenant.membership import Membership

router = APIRouter(tags=["tenant-members"])
container = build_container()
service = container.get(TenantMembershipService)


def _member(membership: Membership, email: str | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "id": membership.id.value,
        "user_id": membership.user_id.value,
        "role": membership.role.value,
        "status": membership.status.value,
        "created_at": membership.created_at.isoformat(),
        "updated_at": membership.updated_at.isoformat(),
    }
    if email is not None:
        data["email"] = email
    return data


def _envelope(request: Request, data: object) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": data,
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.get("/tenants/{slug}/members", status_code=status.HTTP_200_OK)
async def list_members(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_READ)),
) -> JSONResponse:
    members = await service.list(context, status_filter)
    return _envelope(request, [_member(m.membership, m.email) for m in members])


@router.patch("/tenants/{slug}/members/{membership_id}", status_code=status.HTTP_200_OK)
async def change_member_role(
    request: Request,
    membership_id: str,
    payload: dict[str, object],
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_MANAGE)),
) -> JSONResponse:
    role = payload.get("role")
    if not isinstance(role, str):
        raise AppError("role must be a string", status_code=422)
    return _envelope(request, _member(await service.change_role(context, membership_id, role)))


@router.delete("/tenants/{slug}/members/{membership_id}", status_code=status.HTTP_200_OK)
async def revoke_member(
    request: Request,
    membership_id: str,
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_MANAGE)),
) -> JSONResponse:
    return _envelope(request, _member(await service.revoke(context, membership_id)))


@router.post("/tenants/{slug}/members/{membership_id}/reactivate", status_code=status.HTTP_200_OK)
async def reactivate_member(
    request: Request,
    membership_id: str,
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_MANAGE)),
) -> JSONResponse:
    return _envelope(request, _member(await service.reactivate(context, membership_id)))

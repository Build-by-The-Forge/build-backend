from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.application.identity.throttle import AuthThrottle
from app.application.tenant.invitation_service import TenantInvitationService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import get_verified_principal, require_tenant_permission
from app.core.exceptions import AppError
from app.core.principal import AuthenticatedPrincipal
from app.core.request_context import client_ip
from app.core.tenant_context import TenantContext
from app.domain.tenant.invitation import TenantInvitation

router = APIRouter(tags=["tenant-invitations"])
container = build_container()
service = container.get(TenantInvitationService)
throttle = container.get(AuthThrottle)


def _envelope(request: Request, data: object, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _invitation(invitation: TenantInvitation) -> dict[str, object]:
    # Never the token or its hash.
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role.value,
        "status": invitation.status.value,
        "invited_by_user_id": invitation.invited_by_user_id,
        "expires_at": invitation.expires_at.isoformat(),
        "created_at": invitation.created_at.isoformat(),
        "accepted_at": invitation.accepted_at.isoformat() if invitation.accepted_at else None,
        "revoked_at": invitation.revoked_at.isoformat() if invitation.revoked_at else None,
    }


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise AppError(f"{key} must be a string", status_code=422)
    return value


@router.post("/tenants/{slug}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    request: Request,
    payload: dict[str, object],
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_INVITE)),
) -> JSONResponse:
    await throttle.create_invitation(context.user_id)
    invitation = await service.invite(context, _text(payload, "email"), _text(payload, "role"))
    return _envelope(request, _invitation(invitation), status.HTTP_201_CREATED)


@router.get("/tenants/{slug}/invitations", status_code=status.HTTP_200_OK)
async def list_invitations(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_INVITE)),
) -> JSONResponse:
    invitations = await service.list(context, status_filter)
    return _envelope(request, [_invitation(i) for i in invitations])


@router.delete("/tenants/{slug}/invitations/{invitation_id}", status_code=status.HTTP_200_OK)
async def revoke_invitation(
    request: Request,
    invitation_id: str,
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_MEMBER_INVITE)),
) -> JSONResponse:
    invitation = await service.revoke(context, invitation_id)
    return _envelope(request, _invitation(invitation))


@router.post("/invitations/accept", status_code=status.HTTP_200_OK)
async def accept_invitation(
    request: Request,
    payload: dict[str, object],
    principal: AuthenticatedPrincipal = Depends(get_verified_principal),
) -> JSONResponse:
    await throttle.accept_invitation(client_ip(request))
    accepted = await service.accept(principal.user_id, _text(payload, "token"))
    return _envelope(
        request,
        {
            "tenant_id": accepted.tenant_id,
            "tenant_slug": accepted.tenant_slug,
            "membership_id": accepted.membership_id,
            "role": accepted.role.value,
            "reactivated": accepted.reactivated,
        },
    )

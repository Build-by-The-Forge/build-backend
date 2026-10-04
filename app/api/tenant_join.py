from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.application.identity.throttle import AuthThrottle
from app.application.tenant.join_service import JoinResult, TenantJoinService
from app.bootstrap.container import build_container
from app.core.authorization import Permission
from app.core.dependencies import get_verified_principal, require_tenant_permission
from app.core.exceptions import AppError
from app.core.principal import AuthenticatedPrincipal
from app.core.request_context import client_ip
from app.core.tenant_context import TenantContext
from app.domain.tenant.join_policy import TenantJoinPolicy

router = APIRouter(tags=["tenant-join"])
container = build_container()
service = container.get(TenantJoinService)
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


def _policy(policy: TenantJoinPolicy) -> dict[str, object]:
    return {
        "enabled": policy.enabled,
        "allowed_domains": list(policy.allowed_domains),
        "default_role": policy.default_role.value,
        "updated_at": policy.updated_at.isoformat(),
    }


def _joined(result: JoinResult) -> dict[str, object]:
    return {
        "tenant_id": result.tenant_id,
        "tenant_slug": result.tenant_slug,
        "membership_id": result.membership.id.value,
        "role": result.membership.role.value,
        "created": result.created,
    }


@router.post("/tenants/{slug}/join", status_code=status.HTTP_200_OK)
async def join_tenant(
    request: Request,
    slug: str,
    principal: AuthenticatedPrincipal = Depends(get_verified_principal),
) -> JSONResponse:
    await throttle.domain_join(client_ip(request))
    result = await service.join(principal.user_id, slug)
    return _envelope(request, _joined(result), status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)


@router.get("/tenants/{slug}/join-policy", status_code=status.HTTP_200_OK)
async def get_join_policy(
    request: Request,
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_SETTINGS_MANAGE)),
) -> JSONResponse:
    return _envelope(request, _policy(await service.get_policy(context)))


@router.put("/tenants/{slug}/join-policy", status_code=status.HTTP_200_OK)
async def set_join_policy(
    request: Request,
    payload: dict[str, object],
    context: TenantContext = Depends(require_tenant_permission(Permission.TENANT_SETTINGS_MANAGE)),
) -> JSONResponse:
    enabled = payload.get("enabled")
    domains = payload.get("allowed_domains", [])
    default_role = payload.get("default_role", "student")
    if (
        not isinstance(enabled, bool)
        or not isinstance(domains, list)
        or not all(isinstance(d, str) for d in domains)
        or not isinstance(default_role, str)
    ):
        raise AppError("expected enabled (bool), allowed_domains (list of strings), default_role (string)", status_code=422)
    policy = await service.set_policy(context, enabled=enabled, allowed_domains=domains, default_role=default_role)
    return _envelope(request, _policy(policy))

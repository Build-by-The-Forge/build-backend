from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status

from app.application.identity.ports.token_service import InvalidTokenError
from app.core.authorization import Permission, authorization
from app.core.principal import AuthenticatedPrincipal
from app.core.tenant_context import TenantContext
from app.db.session import SessionLocal
from app.infrastructure.identity.sqlalchemy_session_repository import (
    SQLAlchemySessionRepository,
)
from app.infrastructure.identity.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.jwt_token_service import JWTTokenService
from app.infrastructure.tenant.async_repositories import (
    AsyncSqlAlchemyMembershipRepository,
    AsyncSqlAlchemyTenantRepository,
)
from app.infrastructure.unit_of_work import UnitOfWork


async def get_unit_of_work() -> AsyncIterator[UnitOfWork]:
    async with SessionLocal() as session:
        async with UnitOfWork(session) as uow:
            yield uow


_token_service = JWTTokenService()


def _unauthorized(detail: str = "invalid token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_principal(
    request: Request, uow: UnitOfWork = Depends(get_unit_of_work)
) -> AuthenticatedPrincipal:
    """The single authentication path: verify the signed access token
    (Authorization: Bearer <jwt>) and return the authenticated principal."""
    auth = request.headers.get("authorization")
    if auth is None or not auth.startswith("Bearer "):
        raise _unauthorized("missing bearer token")

    try:
        claims = _token_service.decode_access_token(auth.split(" ", 1)[1])
    except InvalidTokenError:
        raise _unauthorized() from None

    # Checked on every request so logout, revocation, expiry and account
    # disablement take effect immediately, not when the token expires.
    session = await SQLAlchemySessionRepository(uow.session).get_by_id(claims.session_id)
    if (
        session is None
        or session.user_id.value != claims.user_id
        or not session.is_active_at(datetime.now(timezone.utc))
    ):
        raise _unauthorized()

    user = await SQLAlchemyUserRepository(uow.session).get_by_id(claims.user_id)
    if user is None or not user.can_authenticate:
        raise _unauthorized()

    return AuthenticatedPrincipal(
        user_id=user.id.value,
        session_id=claims.session_id,
        email_verified=user.email_verified,
    )


def _verification_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="email verification required",
    )


async def get_verified_principal(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """For actions that need a verified email outside a tenant (e.g. accepting
    an invitation)."""
    if not principal.email_verified:
        raise _verification_required()
    return principal


async def get_current_tenant_context(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_verified_principal),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TenantContext:
    tenant_slug = request.headers.get("x-tenant-slug")
    if not tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant context is required",
        )
    return await _resolve_tenant_context(tenant_slug, principal, uow)


async def get_path_tenant_context(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(get_verified_principal),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TenantContext:
    """Tenant context for /tenants/{slug}/... routes: the path names the
    tenant and any x-tenant-slug header is ignored."""
    return await _resolve_tenant_context(slug, principal, uow)


async def _resolve_tenant_context(
    tenant_slug: str, principal: AuthenticatedPrincipal, uow: UnitOfWork
) -> TenantContext:
    tenant_slug = tenant_slug.strip().lower()

    tenant = await AsyncSqlAlchemyTenantRepository(uow.session).get_by_slug(tenant_slug)
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant access denied",
        )

    membership = await AsyncSqlAlchemyMembershipRepository(
        uow.session
    ).get_by_tenant_user(tenant.id.value, principal.user_id)
    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant access denied",
        )

    return TenantContext(
        user_id=principal.user_id,
        tenant_id=tenant.id.value,
        membership_id=membership.id.value,
        role=membership.role.value,
    )


def require_tenant_permission(
    permission: Permission,
) -> Callable[..., Awaitable[TenantContext]]:
    """require_permission for /tenants/{slug}/... routes."""

    async def dependency(
        context: TenantContext = Depends(get_path_tenant_context),
    ) -> TenantContext:
        if not authorization.can(context, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="permission denied",
            )
        return context

    return dependency


def require_permission(
    permission: Permission,
) -> Callable[..., Awaitable[TenantContext]]:
    async def dependency(
        context: TenantContext = Depends(get_current_tenant_context),
    ) -> TenantContext:
        if not authorization.can(context, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="permission denied",
            )
        return context

    return dependency

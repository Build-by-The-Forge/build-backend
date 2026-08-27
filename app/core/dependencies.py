from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status

from app.bootstrap.container import build_container
from app.core.authorization import Permission, authorization
from app.core.principal import AuthenticatedPrincipal
from app.core.tenant_context import TenantContext
from app.db.session import SessionLocal
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


async def get_current_principal(
    request: Request, uow: UnitOfWork = Depends(get_unit_of_work)
) -> AuthenticatedPrincipal:
    """Authenticate request via Authorization: Bearer <token> and return principal.

    This reuses the existing JWTTokenService and verifies the user exists.
    """
    auth = request.headers.get("authorization")
    if auth is None or not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token"
        )

    token = auth.split(" ", 1)[1]
    container = build_container()
    token_service: JWTTokenService = container.get(JWTTokenService)

    try:
        valid = token_service.validate(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )

    decoded = token_service.decode(token)
    user_id = decoded.get("sub") if isinstance(decoded, dict) else None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )

    # normalise access/refresh prefixes used by JWTTokenService implementations
    if isinstance(user_id, str) and (
        user_id.startswith("access:") or user_id.startswith("refresh:")
    ):
        user_id = user_id.split(":", 1)[1]

    # verify user exists
    repo = SQLAlchemyUserRepository(uow.session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )

    return AuthenticatedPrincipal(user_id=user.id.value)


async def get_current_tenant_context(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TenantContext:
    tenant_slug = request.headers.get("x-tenant-slug")
    if not tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant context is required",
        )
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

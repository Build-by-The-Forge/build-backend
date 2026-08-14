from collections.abc import AsyncIterator

from app.db.session import SessionLocal
from app.infrastructure.unit_of_work import UnitOfWork
from fastapi import Depends, HTTPException, Request, status

from app.bootstrap.container import build_container
from app.core.principal import AuthenticatedPrincipal
from app.infrastructure.identity.sqlalchemy_user_repository import SQLAlchemyUserRepository
from app.infrastructure.security.jwt_token_service import JWTTokenService


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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    token = auth.split(" ", 1)[1]
    container = build_container()
    token_service: JWTTokenService = container.get(JWTTokenService)

    try:
        valid = token_service.validate(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    decoded = token_service.decode(token)
    user_id = decoded.get("sub") if isinstance(decoded, dict) else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    # normalise access/refresh prefixes used by JWTTokenService implementations
    if isinstance(user_id, str) and (user_id.startswith("access:") or user_id.startswith("refresh:")):
        user_id = user_id.split(":", 1)[1]

    # verify user exists
    repo = SQLAlchemyUserRepository(uow.session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    return AuthenticatedPrincipal(user_id=user.id.value)

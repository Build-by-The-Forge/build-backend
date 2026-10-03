from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.application.identity.handlers import IssuedSession
from app.application.identity.user_service import UserService
from app.bootstrap.container import build_container
from app.core.authorization import Permission, authorization
from app.core.config import settings
from app.core.dependencies import (
    get_current_principal,
    get_current_tenant_context,
    require_permission,
)
from app.core.exceptions import AppError
from app.core.principal import AuthenticatedPrincipal
from app.core.tenant_context import TenantContext

router = APIRouter(prefix="/identity", tags=["identity"])
container = build_container()
service = container.get(UserService)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def register_user(request: Request, payload: dict[str, str]) -> JSONResponse:
    email = payload.get("email", "")
    password = payload.get("password", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        user = await service.register_user(email, password)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "data": {
                "id": user.id.value,
                "email": user.email.value,
                "is_active": user.is_active,
            },
            "meta": {},
            "request_id": request_id,
        },
    )


@router.post("/authenticate", status_code=status.HTTP_200_OK)
async def authenticate_user(request: Request, payload: dict[str, str]) -> JSONResponse:
    email = payload.get("email", "")
    password = payload.get("password", "")
    device_id = payload.get("device_id")
    user_agent = payload.get("user_agent")
    request_id = getattr(request.state, "request_id", None)

    try:
        issued = await service.authenticate_user(
            email, password, device_id=device_id, user_agent=user_agent
        )
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return _issued_session_response(issued, request_id)


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_session(request: Request, payload: dict[str, str]) -> JSONResponse:
    refresh_token = payload.get("refresh_token", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        issued = await service.refresh_session(refresh_token)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return _issued_session_response(issued, request_id)


def _issued_session_response(issued: IssuedSession, request_id: str | None) -> JSONResponse:
    session = issued.session
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "user_id": session.user_id.value,
                "session_id": session.id.value,
                "device_id": session.device_id.value if session.device_id else None,
                "access_token": service.token_service.issue_access_token(
                    session.user_id.value, session.id.value
                ),
                "token_type": "Bearer",
                "expires_in": settings.auth_access_token_ttl_seconds,
                "refresh_token": issued.refresh_token,
            },
            "meta": {},
            "request_id": request_id,
        },
    )


@router.post("/logout-all", status_code=status.HTTP_200_OK)
async def logout_all_sessions(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    revoked = await service.logout_all_sessions(principal.user_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"revoked_sessions": revoked},
            "meta": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout_session(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)

    try:
        await service.logout_session(principal.session_id, principal.user_id)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "data": {}, "meta": {}, "request_id": request_id},
    )


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(request: Request, payload: dict[str, str]) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)

    try:
        user = await service.verify_email(payload.get("token", ""))
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"email_verified": user.email_verified},
            "meta": {},
            "request_id": request_id,
        },
    )


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(request: Request, payload: dict[str, str]) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)

    try:
        await service.request_email_verification(payload.get("email", ""))
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {},
            "meta": {
                "message": "If this email needs verification, a new code has been sent."
            },
            "request_id": request_id,
        },
    )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(request: Request, payload: dict[str, str]) -> JSONResponse:
    email = payload.get("email", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        await service.forgot_password(email)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {},
            "meta": {
                "message": "If an account exists for this email, a reset code has been sent."
            },
            "request_id": request_id,
        },
    )


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: Request, payload: dict[str, str]) -> JSONResponse:
    token = payload.get("token", "")
    password = payload.get("password", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        await service.reset_password(token, password)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "data": {}, "meta": {}, "request_id": request_id},
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    request: Request,
    payload: dict[str, object],
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    current_password = payload.get("current_password", "")
    new_password = payload.get("new_password", "")
    revoke_other_sessions = payload.get("revoke_other_sessions", True)

    try:
        if not (
            isinstance(current_password, str)
            and isinstance(new_password, str)
            and isinstance(revoke_other_sessions, bool)
        ):
            raise AppError("invalid change-password payload", status_code=422)
        revoked = await service.change_password(
            principal.user_id,
            principal.session_id,
            current_password,
            new_password,
            revoke_other_sessions=revoke_other_sessions,
        )
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"revoked_sessions": revoked},
            "meta": {},
            "request_id": request_id,
        },
    )


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)

    try:
        user = await service.get_current_user(principal.user_id)
    except AppError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": {},
                "meta": {"error": str(exc)},
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "id": user.id.value,
                "email": user.email.value,
                "is_active": user.is_active,
            },
            "meta": {},
            "request_id": request_id,
        },
    )


@router.get("/whoami", status_code=status.HTTP_200_OK)
async def whoami(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {"user_id": principal.user_id},
            "meta": {},
        },
    )


@router.get("/tenant-context", status_code=status.HTTP_200_OK)
async def get_tenant_context(
    context: TenantContext = Depends(get_current_tenant_context),
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "user_id": context.user_id,
                "tenant_id": context.tenant_id,
                "membership_id": context.membership_id,
                "role": context.role,
            },
            "meta": {},
        },
    )


@router.get("/permissions", status_code=status.HTTP_200_OK)
async def get_permissions(
    context: TenantContext = Depends(get_current_tenant_context),
) -> JSONResponse:
    permissions = sorted(
        permission.value for permission in authorization.permissions_for(context)
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "tenant_id": context.tenant_id,
                "role": context.role,
                "permissions": permissions,
            },
            "meta": {},
        },
    )


@router.get("/authorization-probe", status_code=status.HTTP_200_OK)
async def authorization_probe(
    context: TenantContext = Depends(require_permission(Permission.CATALOGUE_CREATE)),
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "tenant_id": context.tenant_id,
                "role": context.role,
                "permission": Permission.CATALOGUE_CREATE.value,
            },
            "meta": {},
        },
    )

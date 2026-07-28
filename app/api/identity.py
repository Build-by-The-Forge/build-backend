from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.application.identity.user_service import UserService
from app.bootstrap.container import build_container
from app.core.exceptions import AppError

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
            "data": {"id": user.id.value, "email": user.email.value, "is_active": user.is_active},
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
        session = await service.authenticate_user(email, password, device_id=device_id, user_agent=user_agent)
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

    access_token = service.token_service.issue_access_token(session.user_id.value)
    refresh_token = session.refresh_token_hash.value if session.refresh_token_hash else None

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "user_id": session.user_id.value,
                "session_id": session.id.value,
                "device_id": session.device_id.value if session.device_id else None,
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
            "meta": {},
            "request_id": request_id,
        },
    )


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_session(request: Request, payload: dict[str, str]) -> JSONResponse:
    session_id = payload.get("session_id", "")
    refresh_token = payload.get("refresh_token", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        session = await service.refresh_session(session_id, refresh_token)
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

    access_token = service.token_service.issue_access_token(session.user_id.value)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "user_id": session.user_id.value,
                "session_id": session.id.value,
                "access_token": access_token,
            },
            "meta": {},
            "request_id": request_id,
        },
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout_session(request: Request, payload: dict[str, str]) -> JSONResponse:
    session_id = payload.get("session_id", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        await service.logout_session(session_id)
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


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)

    if authorization is None or not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "data": {}, "meta": {"error": "missing bearer token"}, "request_id": request_id},
        )

    token = authorization.split(" ", 1)[1]
    decoded = service.token_service.decode(token)
    user_id = decoded.get("sub")
    if user_id is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "data": {}, "meta": {"error": "invalid token"}, "request_id": request_id},
        )

    if user_id.startswith("access:"):
        user_id = user_id.split(":", 1)[1]

    if user_id.startswith("refresh:"):
        user_id = user_id.split(":", 1)[1]

    if user_id is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "data": {}, "meta": {"error": "invalid token"}, "request_id": request_id},
        )

    try:
        user = await service.get_current_user(user_id)
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
            "data": {"id": user.id.value, "email": user.email.value, "is_active": user.is_active},
            "meta": {},
            "request_id": request_id,
        },
    )

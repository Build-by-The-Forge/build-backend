from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.application.identity.user_service import UserService
from app.core.exceptions import AppError
from app.events.event_bus import EventBus
from app.infrastructure.identity.memory_user_repository import InMemoryUserRepository

router = APIRouter(prefix="/identity", tags=["identity"])
repository = InMemoryUserRepository()
event_bus = EventBus()
service = UserService(repository=repository, event_bus=event_bus)


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

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "data": {
                "user_id": session.user_id.value,
                "session_id": session.id.value,
                "device_id": session.device_id.value if session.device_id else None,
            },
            "meta": {},
            "request_id": request_id,
        },
    )

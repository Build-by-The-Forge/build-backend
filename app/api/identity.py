from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.application.identity.user_service import UserService
from app.core.exceptions import AppError
from app.infrastructure.identity.memory_user_repository import InMemoryUserRepository

router = APIRouter(prefix="/identity", tags=["identity"])
repository = InMemoryUserRepository()
service = UserService(repository)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def register_user(request: Request, payload: dict[str, str]) -> JSONResponse:
    email = payload.get("email", "")
    password = payload.get("password", "")
    request_id = getattr(request.state, "request_id", None)

    try:
        user = await service.register_user(email, password)
    except AppError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
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
            "data": {"id": user.id, "email": user.email, "is_active": user.is_active},
            "meta": {},
            "request_id": request_id,
        },
    )

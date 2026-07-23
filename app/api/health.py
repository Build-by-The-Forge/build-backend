from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/startup")
def startup() -> dict[str, str]:
    return {"status": "startup"}

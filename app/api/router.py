from fastapi import APIRouter

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/health/startup")
def startup() -> dict[str, str]:
    return {"status": "startup"}

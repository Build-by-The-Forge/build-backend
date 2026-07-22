from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import configure_logging
from app.api.health import router as health_router

configure_logging()

app = FastAPI(title="BUILD Backend", version="0.1.0")
app.include_router(health_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "BUILD backend is running", "environment": settings.app_environment}

from fastapi import APIRouter

from app.api.content.assets import router as assets_router
from app.api.content.jobs import router as jobs_router
from app.api.content.sources import router as sources_router

router = APIRouter(prefix="/content", tags=["content"])
router.include_router(sources_router)
router.include_router(assets_router)
router.include_router(jobs_router)

__all__ = ["router"]

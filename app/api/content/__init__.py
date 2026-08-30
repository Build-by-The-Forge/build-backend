from fastapi import APIRouter

from app.api.content.sources import router as sources_router

router = APIRouter(prefix="/content", tags=["content"])
router.include_router(sources_router)

__all__ = ["router"]

from fastapi import APIRouter

from app.api.catalogue import courses_router

router = APIRouter()
router.include_router(courses_router)

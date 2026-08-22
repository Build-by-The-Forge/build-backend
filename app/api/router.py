from fastapi import APIRouter

from app.api.catalogue import courses_router, topic_router

router = APIRouter()
router.include_router(courses_router)
router.include_router(topic_router)

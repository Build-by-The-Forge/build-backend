from fastapi import APIRouter

from app.api.ai import router as ai_router
from app.api.assessment import assessment_router, attempt_router, question_router
from app.api.assessment.answers import router as answer_router
from app.api.catalogue import (
    courses_router,
    learning_outcome_router,
    reference_router,
    topic_router,
)
from app.api.content import router as content_router
from app.api.curriculum import (
    curriculum_adoptions_router,
    curriculum_benchmarks_router,
    curriculum_sources_router,
)

router = APIRouter()
router.include_router(courses_router)
router.include_router(topic_router)
router.include_router(learning_outcome_router)
router.include_router(reference_router)
router.include_router(question_router)
router.include_router(assessment_router)
router.include_router(attempt_router)
router.include_router(answer_router)
router.include_router(curriculum_sources_router)
router.include_router(curriculum_benchmarks_router)
router.include_router(curriculum_adoptions_router)
router.include_router(content_router)
router.include_router(ai_router)

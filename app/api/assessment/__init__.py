from app.api.assessment.assessments import router as assessment_router
from app.api.assessment.attempts import router as attempt_router
from app.api.assessment.questions import router as question_router

__all__ = ["question_router", "assessment_router", "attempt_router"]

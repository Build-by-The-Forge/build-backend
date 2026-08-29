from app.api.catalogue.courses import (
    learning_outcome_router,
    reference_router,
    topic_router,
)
from app.api.catalogue.courses import router as courses_router

__all__ = [
    "courses_router",
    "topic_router",
    "learning_outcome_router",
    "reference_router",
]

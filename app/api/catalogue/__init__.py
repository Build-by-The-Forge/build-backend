from app.api.catalogue.courses import (
    learning_outcome_router,
    reference_router,
    topic_router,
)
from app.api.catalogue.courses import router as courses_router
from app.api.catalogue.structure import router as structure_router

__all__ = [
    "courses_router",
    "structure_router",
    "topic_router",
    "learning_outcome_router",
    "reference_router",
]

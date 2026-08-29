from app.api.curriculum.adoptions import (
    router as curriculum_adoptions_router,
)
from app.api.curriculum.benchmarks import (
    router as curriculum_benchmarks_router,
)
from app.api.curriculum.sources import router as curriculum_sources_router

__all__ = [
    "curriculum_sources_router",
    "curriculum_benchmarks_router",
    "curriculum_adoptions_router",
]

from __future__ import annotations

from app.application.curriculum.effective_queries import (
    GetActiveEffectiveCurriculumQuery,
    GetEffectiveCurriculumByAdoptionQuery,
)
from app.domain.curriculum.benchmark import BenchmarkCourse
from app.domain.curriculum.effective import (
    EffectiveCurriculum,
    EffectiveCurriculumResolver,
)
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.domain.repositories.institutional_adoption import (
    InstitutionalAdoptionRepository,
)


class GetEffectiveCurriculumByAdoptionHandler:
    def __init__(
        self,
        adoption_repo: InstitutionalAdoptionRepository,
        benchmark_repo: BenchmarkCurriculumRepository,
    ) -> None:
        self.adoption_repo = adoption_repo
        self.benchmark_repo = benchmark_repo
        self.resolver = EffectiveCurriculumResolver()

    async def handle(self, query: GetEffectiveCurriculumByAdoptionQuery) -> EffectiveCurriculum:
        adoption = await self.adoption_repo.get_adoption_by_id(query.adoption_id)
        if adoption is None or adoption.tenant_id != query.tenant_id:
            raise ValueError("adoption not found")

        benchmark = await self.benchmark_repo.get_by_id(adoption.benchmark_curriculum_id)
        if benchmark is None:
            raise ValueError("benchmark curriculum not found")

        course_summaries = await self.benchmark_repo.list_courses(benchmark.id)
        full_courses: list[BenchmarkCourse] = []
        for s in course_summaries:
            course = await self.benchmark_repo.get_course(s.id)
            if course is not None:
                full_courses.append(course)

        overrides = await self.adoption_repo.list_overrides(adoption.id)

        return self.resolver.resolve(
            adoption=adoption,
            benchmark=benchmark,
            benchmark_courses=full_courses,
            overrides=overrides,
        )


class GetActiveEffectiveCurriculumHandler:
    def __init__(
        self,
        adoption_repo: InstitutionalAdoptionRepository,
        benchmark_repo: BenchmarkCurriculumRepository,
    ) -> None:
        self.adoption_repo = adoption_repo
        self.benchmark_repo = benchmark_repo
        self.resolver = EffectiveCurriculumResolver()

    async def handle(self, query: GetActiveEffectiveCurriculumQuery) -> EffectiveCurriculum:
        adoption = await self.adoption_repo.get_active_adoption(
            tenant_id=query.tenant_id,
            programme_id=query.programme_id,
            academic_session_id=query.academic_session_id,
        )
        if adoption is None:
            raise ValueError(f"no active curriculum adoption found for programme '{query.programme_id}'")

        benchmark = await self.benchmark_repo.get_by_id(adoption.benchmark_curriculum_id)
        if benchmark is None:
            raise ValueError("benchmark curriculum not found")

        course_summaries = await self.benchmark_repo.list_courses(benchmark.id)
        full_courses: list[BenchmarkCourse] = []
        for s in course_summaries:
            course = await self.benchmark_repo.get_course(s.id)
            if course is not None:
                full_courses.append(course)

        overrides = await self.adoption_repo.list_overrides(adoption.id)

        return self.resolver.resolve(
            adoption=adoption,
            benchmark=benchmark,
            benchmark_courses=full_courses,
            overrides=overrides,
        )

from __future__ import annotations

from app.application.curriculum.diff_commands import (
    CompareBenchmarkCurriculaCommand,
)
from app.domain.curriculum.benchmark import BenchmarkCourse
from app.domain.curriculum.diff import (
    BenchmarkCurriculumDiff,
    BenchmarkCurriculumDiffEngine,
)
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)


class CompareBenchmarkCurriculaHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository
        self.engine = BenchmarkCurriculumDiffEngine()

    async def handle(
        self, command: CompareBenchmarkCurriculaCommand
    ) -> BenchmarkCurriculumDiff:
        source_curriculum = await self.repository.get_by_id(
            command.source_curriculum_id
        )
        if source_curriculum is None:
            raise ValueError(
                f"source benchmark curriculum '{command.source_curriculum_id}' not found"
            )

        target_curriculum = await self.repository.get_by_id(
            command.target_curriculum_id
        )
        if target_curriculum is None:
            raise ValueError(
                f"target benchmark curriculum '{command.target_curriculum_id}' not found"
            )

        # Validate both belong to the same benchmark identity
        if (
            source_curriculum.discipline_group != target_curriculum.discipline_group
            or source_curriculum.programme_code != target_curriculum.programme_code
            or source_curriculum.degree_level != target_curriculum.degree_level
        ):
            raise ValueError(
                f"cannot compare curricula of different programmes "
                f"('{source_curriculum.discipline_group}/{source_curriculum.programme_code}' vs "
                f"'{target_curriculum.discipline_group}/{target_curriculum.programme_code}')"
            )

        source_courses = await self._load_full_courses(source_curriculum.id)
        target_courses = await self._load_full_courses(target_curriculum.id)

        return self.engine.compare(
            source_curriculum=source_curriculum,
            source_courses=source_courses,
            target_curriculum=target_curriculum,
            target_courses=target_courses,
        )

    async def _load_full_courses(self, curriculum_id: str) -> list[BenchmarkCourse]:
        summaries = await self.repository.list_courses(curriculum_id)
        full_courses: list[BenchmarkCourse] = []
        for s in summaries:
            course = await self.repository.get_course(s.id)
            if course is not None:
                full_courses.append(course)
        return full_courses

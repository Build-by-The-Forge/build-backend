from __future__ import annotations

from app.application.curriculum.validation_commands import (
    ValidateBenchmarkCandidateCommand,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkStatus,
)
from app.domain.curriculum.validator import (
    BenchmarkCurriculumValidator,
    ValidationResult,
)
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent


class ValidateBenchmarkCandidateHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository
        self.validator = BenchmarkCurriculumValidator()

    async def handle(
        self, command: ValidateBenchmarkCandidateCommand
    ) -> tuple[BenchmarkCurriculum, ValidationResult, list[DomainEvent]]:
        curriculum = await self.repository.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        # Load all courses with full topic and outcome trees
        course_summaries = await self.repository.list_courses(curriculum.id)
        full_courses: list[BenchmarkCourse] = []
        for summary in course_summaries:
            course = await self.repository.get_course(summary.id)
            if course is not None:
                full_courses.append(course)

        validation_result = self.validator.validate(curriculum, full_courses)

        events: list[DomainEvent] = []
        if (
            validation_result.is_valid
            and curriculum.status == BenchmarkStatus.CANDIDATE
        ):
            curriculum.mark_validated()
            await self.repository.save(curriculum)
            events = curriculum.pull_events()

        return curriculum, validation_result, events

from __future__ import annotations

from app.application.curriculum.benchmark_commands import (
    GetBenchmarkCourseCommand,
    GetBenchmarkCurriculumCommand,
    IngestBenchmarkCandidateCommand,
    ListBenchmarkCoursesCommand,
    ListBenchmarkCurriculaCommand,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent


class IngestBenchmarkCandidateHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository

    async def handle(self, command: IngestBenchmarkCandidateCommand) -> tuple[BenchmarkCurriculum, bool, list[DomainEvent]]:
        # 1. Check for duplicate candidate for this snapshot and programme
        existing = await self.repository.get_by_snapshot_and_programme(
            source_snapshot_id=command.source_snapshot_id,
            programme_code=command.programme_code,
        )
        if existing is not None:
            return existing, False, []

        # 2. Intra-candidate uniqueness validations
        seen_codes: set[str] = set()
        seen_sequences: set[int] = set()
        for course_input in command.courses:
            clean_code = course_input.code.strip().upper()
            if clean_code in seen_codes:
                raise ValueError(f"duplicate course code '{clean_code}' in candidate payload")
            seen_codes.add(clean_code)

            if course_input.sequence in seen_sequences:
                raise ValueError(f"duplicate course sequence '{course_input.sequence}' in candidate payload")
            seen_sequences.add(course_input.sequence)

            seen_topic_sequences: set[int] = set()
            for topic_input in course_input.topics:
                if topic_input.sequence in seen_topic_sequences:
                    raise ValueError(f"duplicate topic sequence '{topic_input.sequence}' in course '{clean_code}'")
                seen_topic_sequences.add(topic_input.sequence)

                seen_outcome_sequences: set[int] = set()
                for outcome_input in topic_input.outcomes:
                    if outcome_input.sequence in seen_outcome_sequences:
                        raise ValueError(
                            f"duplicate outcome sequence '{outcome_input.sequence}' in topic '{topic_input.sequence}'"
                        )
                    seen_outcome_sequences.add(outcome_input.sequence)

        # 3. Create Benchmark Curriculum Aggregate Header
        curriculum = BenchmarkCurriculum.create_candidate(
            source_snapshot_id=command.source_snapshot_id,
            discipline_group=command.discipline_group,
            programme_name=command.programme_name,
            programme_code=command.programme_code,
            version=command.version,
            degree_level=command.degree_level,
            minimum_credit_units=command.minimum_credit_units,
        )
        await self.repository.save(curriculum)

        # 4. Construct and persist courses with topics and outcomes
        for course_input in command.courses:
            course = BenchmarkCourse.create(
                benchmark_curriculum_id=curriculum.id,
                code=course_input.code,
                title=course_input.title,
                credit_units=course_input.credit_units,
                level=course_input.level,
                semester=course_input.semester,
                is_compulsory=course_input.is_compulsory,
                course_category=course_input.course_category,
                description=course_input.description,
                sequence=course_input.sequence,
            )
            for topic_input in course_input.topics:
                topic = BenchmarkTopic.create(
                    benchmark_course_id=course.id,
                    sequence=topic_input.sequence,
                    title=topic_input.title,
                    description=topic_input.description,
                )
                for outcome_input in topic_input.outcomes:
                    bloom = None
                    if outcome_input.bloom_level:
                        try:
                            bloom = BloomTaxonomyLevel(outcome_input.bloom_level.lower())
                        except ValueError:
                            bloom = None
                    outcome = BenchmarkOutcome.create(
                        benchmark_topic_id=topic.id,
                        sequence=outcome_input.sequence,
                        description=outcome_input.description,
                        bloom_level=bloom,
                    )
                    topic.add_outcome(outcome)
                course.add_topic(topic)
            await self.repository.save_course(course)

        events = curriculum.pull_events()
        return curriculum, True, events


class GetBenchmarkCurriculumHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetBenchmarkCurriculumCommand) -> BenchmarkCurriculum | None:
        return await self.repository.get_by_id(command.curriculum_id)


class ListBenchmarkCurriculaHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository

    async def handle(self, command: ListBenchmarkCurriculaCommand) -> list[BenchmarkCurriculum]:
        return await self.repository.list_curricula(
            programme_code=command.programme_code,
            status=command.status,
        )


class ListBenchmarkCoursesHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository

    async def handle(self, command: ListBenchmarkCoursesCommand) -> list[BenchmarkCourse]:
        return await self.repository.list_courses(
            curriculum_id=command.curriculum_id,
            level=command.level,
            semester=command.semester,
        )


class GetBenchmarkCourseHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetBenchmarkCourseCommand) -> BenchmarkCourse | None:
        return await self.repository.get_course(command.course_id)

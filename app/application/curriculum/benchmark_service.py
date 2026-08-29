from app.application.common.uow import CurriculumUnitOfWorkFactory
from app.application.curriculum.activation_commands import (
    ActivateBenchmarkCurriculumCommand,
)
from app.application.curriculum.activation_handlers import (
    ActivateBenchmarkCurriculumHandler,
)
from app.application.curriculum.benchmark_commands import (
    BenchmarkCourseInput,
    GetBenchmarkCourseCommand,
    GetBenchmarkCurriculumCommand,
    IngestBenchmarkCandidateCommand,
    ListBenchmarkCoursesCommand,
    ListBenchmarkCurriculaCommand,
)
from app.application.curriculum.benchmark_handlers import (
    GetBenchmarkCourseHandler,
    GetBenchmarkCurriculumHandler,
    IngestBenchmarkCandidateHandler,
    ListBenchmarkCoursesHandler,
    ListBenchmarkCurriculaHandler,
)
from app.application.curriculum.diff_commands import (
    CompareBenchmarkCurriculaCommand,
)
from app.application.curriculum.diff_handlers import (
    CompareBenchmarkCurriculaHandler,
)
from app.application.curriculum.validation_commands import (
    ValidateBenchmarkCandidateCommand,
)
from app.application.curriculum.validation_handlers import (
    ValidateBenchmarkCandidateHandler,
)
from app.domain.curriculum.benchmark import BenchmarkCourse, BenchmarkCurriculum
from app.domain.curriculum.diff import BenchmarkCurriculumDiff
from app.domain.curriculum.validator import ValidationResult
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class BenchmarkCurriculumService:
    def __init__(
        self,
        repository: BenchmarkCurriculumRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: CurriculumUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def ingest_candidate(
        self,
        source_snapshot_id: str,
        extractor_version: str,
        discipline_group: str,
        programme_name: str,
        programme_code: str,
        version: str,
        degree_level: str = "undergraduate",
        minimum_credit_units: int = 120,
        courses: list[BenchmarkCourseInput] | None = None,
    ) -> tuple[BenchmarkCurriculum, bool]:
        command = IngestBenchmarkCandidateCommand(
            source_snapshot_id=source_snapshot_id,
            extractor_version=extractor_version,
            discipline_group=discipline_group,
            programme_name=programme_name,
            programme_code=programme_code,
            version=version,
            degree_level=degree_level,
            minimum_credit_units=minimum_credit_units,
            courses=courses or [],
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, created, events = await IngestBenchmarkCandidateHandler(
                    uow.benchmarks
                ).handle(command)
            self._publish_events(events)
            return curriculum, created

        curriculum, created, events = await IngestBenchmarkCandidateHandler(
            self._required_repository()
        ).handle(command)
        self._publish_events(events)
        return curriculum, created

    async def get_curriculum(self, curriculum_id: str) -> BenchmarkCurriculum | None:
        command = GetBenchmarkCurriculumCommand(curriculum_id=curriculum_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetBenchmarkCurriculumHandler(uow.benchmarks).handle(
                    command
                )
        return await GetBenchmarkCurriculumHandler(self._required_repository()).handle(
            command
        )

    async def list_curricula(
        self,
        programme_code: str | None = None,
        status: str | None = None,
    ) -> list[BenchmarkCurriculum]:
        command = ListBenchmarkCurriculaCommand(
            programme_code=programme_code, status=status
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListBenchmarkCurriculaHandler(uow.benchmarks).handle(
                    command
                )
        return await ListBenchmarkCurriculaHandler(self._required_repository()).handle(
            command
        )

    async def list_courses(
        self,
        curriculum_id: str,
        level: int | None = None,
        semester: int | None = None,
    ) -> list[BenchmarkCourse]:
        command = ListBenchmarkCoursesCommand(
            curriculum_id=curriculum_id,
            level=level,
            semester=semester,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListBenchmarkCoursesHandler(uow.benchmarks).handle(command)
        return await ListBenchmarkCoursesHandler(self._required_repository()).handle(
            command
        )

    async def get_course(self, course_id: str) -> BenchmarkCourse | None:
        command = GetBenchmarkCourseCommand(course_id=course_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetBenchmarkCourseHandler(uow.benchmarks).handle(command)
        return await GetBenchmarkCourseHandler(self._required_repository()).handle(
            command
        )

    async def validate_candidate(
        self, curriculum_id: str
    ) -> tuple[BenchmarkCurriculum, ValidationResult]:
        command = ValidateBenchmarkCandidateCommand(curriculum_id=curriculum_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, result, events = await ValidateBenchmarkCandidateHandler(
                    uow.benchmarks
                ).handle(command)
            self._publish_events(events)
            return curriculum, result

        curriculum, result, events = await ValidateBenchmarkCandidateHandler(
            self._required_repository()
        ).handle(command)
        self._publish_events(events)
        return curriculum, result

    async def activate_curriculum(
        self,
        curriculum_id: str,
        activated_by: str | None = None,
    ) -> tuple[BenchmarkCurriculum, BenchmarkCurriculum | None]:
        command = ActivateBenchmarkCurriculumCommand(
            curriculum_id=curriculum_id,
            activated_by=activated_by,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, superseded, events = (
                    await ActivateBenchmarkCurriculumHandler(uow.benchmarks).handle(
                        command
                    )
                )
            self._publish_events(events)
            return curriculum, superseded

        curriculum, superseded, events = await ActivateBenchmarkCurriculumHandler(
            self._required_repository()
        ).handle(command)
        self._publish_events(events)
        return curriculum, superseded

    async def get_active_curriculum(
        self,
        discipline_group: str,
        programme_code: str,
        degree_level: str = "undergraduate",
    ) -> BenchmarkCurriculum | None:
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await uow.benchmarks.get_active_by_programme(
                    discipline_group=discipline_group,
                    programme_code=programme_code,
                    degree_level=degree_level,
                )
        return await self._required_repository().get_active_by_programme(
            discipline_group=discipline_group,
            programme_code=programme_code,
            degree_level=degree_level,
        )

    async def compare_curricula(
        self,
        source_curriculum_id: str,
        target_curriculum_id: str,
    ) -> BenchmarkCurriculumDiff:
        command = CompareBenchmarkCurriculaCommand(
            source_curriculum_id=source_curriculum_id,
            target_curriculum_id=target_curriculum_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await CompareBenchmarkCurriculaHandler(uow.benchmarks).handle(
                    command
                )
        return await CompareBenchmarkCurriculaHandler(
            self._required_repository()
        ).handle(command)

    def _required_repository(self) -> BenchmarkCurriculumRepository:
        if self.repository is None:
            raise ValueError("benchmark curriculum repository is required")
        return self.repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

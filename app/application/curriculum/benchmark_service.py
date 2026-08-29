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
from app.application.curriculum.governance_commands import (
    ApproveBenchmarkCommand,
    GetBenchmarkAuditTrailCommand,
    RejectBenchmarkCommand,
    ReviseBenchmarkCommand,
    SubmitBenchmarkReviewCommand,
)
from app.application.curriculum.governance_handlers import (
    ApproveBenchmarkHandler,
    GetBenchmarkAuditTrailHandler,
    RejectBenchmarkHandler,
    ReviseBenchmarkHandler,
    SubmitBenchmarkReviewHandler,
)
from app.application.curriculum.validation_commands import (
    ValidateBenchmarkCandidateCommand,
)
from app.application.curriculum.validation_handlers import (
    ValidateBenchmarkCandidateHandler,
)
from app.domain.curriculum.audit import BenchmarkAuditLog
from app.domain.curriculum.benchmark import BenchmarkCourse, BenchmarkCurriculum
from app.domain.curriculum.diff import BenchmarkCurriculumDiff
from app.domain.curriculum.validator import ValidationResult
from app.domain.repositories.benchmark_audit import BenchmarkAuditRepository
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class BenchmarkCurriculumService:
    def __init__(
        self,
        repository: BenchmarkCurriculumRepository | None = None,
        audit_repository: BenchmarkAuditRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: CurriculumUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
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

    async def submit_for_review(
        self,
        curriculum_id: str,
        actor_id: str,
        actor_email: str,
        notes: str | None = None,
    ) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog]:
        command = SubmitBenchmarkReviewCommand(
            curriculum_id=curriculum_id,
            actor_id=actor_id,
            actor_email=actor_email,
            notes=notes,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, audit_log, events = await SubmitBenchmarkReviewHandler(
                    uow.benchmarks, uow.benchmark_audits
                ).handle(command)
            self._publish_events(events)
            return curriculum, audit_log

        curriculum, audit_log, events = await SubmitBenchmarkReviewHandler(
            self._required_repository(),
            self._required_audit_repository(),
        ).handle(command)
        self._publish_events(events)
        return curriculum, audit_log

    async def approve_curriculum(
        self,
        curriculum_id: str,
        reviewer_id: str,
        reviewer_email: str,
        reason: str,
    ) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog]:
        command = ApproveBenchmarkCommand(
            curriculum_id=curriculum_id,
            reviewer_id=reviewer_id,
            reviewer_email=reviewer_email,
            reason=reason,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, audit_log, events = await ApproveBenchmarkHandler(
                    uow.benchmarks, uow.benchmark_audits
                ).handle(command)
            self._publish_events(events)
            return curriculum, audit_log

        curriculum, audit_log, events = await ApproveBenchmarkHandler(
            self._required_repository(),
            self._required_audit_repository(),
        ).handle(command)
        self._publish_events(events)
        return curriculum, audit_log

    async def reject_curriculum(
        self,
        curriculum_id: str,
        reviewer_id: str,
        reviewer_email: str,
        reason: str,
    ) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog]:
        command = RejectBenchmarkCommand(
            curriculum_id=curriculum_id,
            reviewer_id=reviewer_id,
            reviewer_email=reviewer_email,
            reason=reason,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, audit_log, events = await RejectBenchmarkHandler(
                    uow.benchmarks, uow.benchmark_audits
                ).handle(command)
            self._publish_events(events)
            return curriculum, audit_log

        curriculum, audit_log, events = await RejectBenchmarkHandler(
            self._required_repository(),
            self._required_audit_repository(),
        ).handle(command)
        self._publish_events(events)
        return curriculum, audit_log

    async def revise_curriculum(
        self,
        curriculum_id: str,
        actor_id: str,
        actor_email: str,
        reason: str | None = None,
    ) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog]:
        command = ReviseBenchmarkCommand(
            curriculum_id=curriculum_id,
            actor_id=actor_id,
            actor_email=actor_email,
            reason=reason,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                curriculum, audit_log, events = await ReviseBenchmarkHandler(
                    uow.benchmarks, uow.benchmark_audits
                ).handle(command)
            self._publish_events(events)
            return curriculum, audit_log

        curriculum, audit_log, events = await ReviseBenchmarkHandler(
            self._required_repository(),
            self._required_audit_repository(),
        ).handle(command)
        self._publish_events(events)
        return curriculum, audit_log

    async def get_audit_trail(self, curriculum_id: str) -> list[BenchmarkAuditLog]:
        command = GetBenchmarkAuditTrailCommand(curriculum_id=curriculum_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetBenchmarkAuditTrailHandler(uow.benchmark_audits).handle(
                    command
                )
        return await GetBenchmarkAuditTrailHandler(
            self._required_audit_repository()
        ).handle(command)

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
                    await ActivateBenchmarkCurriculumHandler(
                        uow.benchmarks, uow.benchmark_audits
                    ).handle(command)
                )
            self._publish_events(events)
            return curriculum, superseded

        curriculum, superseded, events = await ActivateBenchmarkCurriculumHandler(
            self._required_repository(),
            self.audit_repository,
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

    def _required_audit_repository(self) -> BenchmarkAuditRepository:
        if self.audit_repository is None:
            raise ValueError("benchmark audit repository is required")
        return self.audit_repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

from app.application.assessment.assessment_commands import (
    AddQuestionToAssessmentCommand,
    CreateAssessmentCommand,
    GetAssessmentCommand,
    GetAssessmentResultsCommand,
    ListAssessmentsCommand,
    PublishAssessmentCommand,
    ReleaseResultsCommand,
    UpdateAssessmentCommand,
)
from app.application.assessment.assessment_handlers import (
    AddQuestionToAssessmentHandler,
    CreateAssessmentHandler,
    GetAssessmentHandler,
    GetAssessmentResultsHandler,
    ListAssessmentsHandler,
    PublishAssessmentHandler,
    ReleaseResultsHandler,
    UpdateAssessmentHandler,
)
from app.application.common.uow import AssessmentUnitOfWorkFactory
from app.domain.assessment.assessment import Assessment
from app.domain.assessment.attempt_policy import AttemptPolicy
from app.domain.assessment.result import AttemptResult
from app.domain.assessment.result_release import ResultRelease
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt_result import AttemptResultRepository
from app.domain.repositories.course import CourseRepository
from app.domain.repositories.question import QuestionRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class AssessmentService:
    def __init__(
        self,
        repository: AssessmentRepository | None = None,
        question_repository: QuestionRepository | None = None,
        catalogue_repository: CourseRepository | None = None,
        attempt_result_repository: AttemptResultRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: AssessmentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.question_repository = question_repository
        self.catalogue_repository = catalogue_repository
        self.attempt_result_repository = attempt_result_repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def create_assessment(
        self,
        tenant_id: str,
        course_id: str,
        title: str,
        instructions: str,
        duration_minutes: int,
        passing_score: int = 0,
        attempt_policy: AttemptPolicy | None = None,
    ) -> Assessment:
        command = CreateAssessmentCommand(
            tenant_id=tenant_id,
            course_id=course_id,
            title=title,
            instructions=instructions,
            duration_minutes=duration_minutes,
            passing_score=passing_score,
            attempt_policy=attempt_policy,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await CreateAssessmentHandler(uow.assessments, uow.catalogue).handle(command)
                events = assessment.pull_events()
            self._publish_events(events)
            return assessment
        assessment = await CreateAssessmentHandler(self._required_repository(), self._required_catalogue_repository()).handle(
            command
        )
        self._publish_events(assessment.pull_events())
        return assessment

    async def get_assessment(self, assessment_id: str, tenant_id: str) -> Assessment | None:
        command = GetAssessmentCommand(assessment_id, tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAssessmentHandler(uow.assessments).handle(command)
        return await GetAssessmentHandler(self._required_repository()).handle(command)

    async def list_assessments(self, tenant_id: str, course_id: str | None = None) -> list[Assessment]:
        command = ListAssessmentsCommand(tenant_id, course_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListAssessmentsHandler(uow.assessments).handle(command)
        return await ListAssessmentsHandler(self._required_repository()).handle(command)

    async def update_assessment(
        self,
        assessment_id: str,
        tenant_id: str,
        title: str | None = None,
        instructions: str | None = None,
        duration_minutes: int | None = None,
        passing_score: int | None = None,
        attempt_policy: AttemptPolicy | None = None,
    ) -> Assessment | None:
        command = UpdateAssessmentCommand(
            assessment_id,
            tenant_id,
            title,
            instructions,
            duration_minutes,
            passing_score,
            attempt_policy,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await UpdateAssessmentHandler(uow.assessments).handle(command)
                events = assessment.pull_events() if assessment is not None else []
            self._publish_events(events)
            return assessment
        assessment = await UpdateAssessmentHandler(self._required_repository()).handle(command)
        if assessment is not None:
            self._publish_events(assessment.pull_events())
        return assessment

    async def publish_assessment(self, assessment_id: str, tenant_id: str) -> Assessment | None:
        command = PublishAssessmentCommand(assessment_id, tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await PublishAssessmentHandler(uow.assessments).handle(command)
                events = assessment.pull_events() if assessment is not None else []
            self._publish_events(events)
            return assessment
        assessment = await PublishAssessmentHandler(self._required_repository()).handle(command)
        if assessment is not None:
            self._publish_events(assessment.pull_events())
        return assessment

    async def add_question(self, assessment_id: str, question_id: str, tenant_id: str) -> Assessment | None:
        command = AddQuestionToAssessmentCommand(assessment_id, question_id, tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await AddQuestionToAssessmentHandler(uow.assessments, uow.questions).handle(command)
                events = assessment.pull_events() if assessment is not None else []
            self._publish_events(events)
            return assessment
        assessment = await AddQuestionToAssessmentHandler(
            self._required_repository(), self._required_question_repository()
        ).handle(command)
        if assessment is not None:
            self._publish_events(assessment.pull_events())
        return assessment

    async def get_assessment_results(
        self,
        assessment_id: str,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AttemptResult], int] | None:
        command = GetAssessmentResultsCommand(
            assessment_id=assessment_id,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAssessmentResultsHandler(uow.assessments, uow.attempt_results).handle(command)
        return await GetAssessmentResultsHandler(self._required_repository(), self._required_attempt_result_repository()).handle(
            command
        )

    async def release_results(self, assessment_id: str, tenant_id: str, released_by: str) -> ResultRelease | None:
        command = ReleaseResultsCommand(assessment_id, tenant_id, released_by)
        if self.uow_factory is None:
            raise ValueError("releasing results needs a unit of work")
        async with self.uow_factory() as uow:
            outcome = await ReleaseResultsHandler(uow.assessments, uow.result_releases).handle(command)
        if outcome is None:
            return None
        release, created = outcome
        if created:
            self._publish_events(
                [
                    DomainEvent(
                        event_type="assessment.results_released",
                        payload={"assessment_id": assessment_id, "tenant_id": tenant_id, "released_by": released_by},
                    )
                ]
            )
        return release

    async def standing_attempts(self, assessment_id: str, tenant_id: str) -> set[str]:
        command = GetAssessmentResultsCommand(assessment_id=assessment_id, tenant_id=tenant_id)
        if self.uow_factory is None:
            raise ValueError("reading results needs a unit of work")
        async with self.uow_factory() as uow:
            return await GetAssessmentResultsHandler(uow.assessments, uow.attempt_results).standing(command)

    def _required_repository(self) -> AssessmentRepository:
        if self.repository is None:
            raise ValueError("assessment repository is required")
        return self.repository

    def _required_question_repository(self) -> QuestionRepository:
        if self.question_repository is None:
            raise ValueError("question repository is required")
        return self.question_repository

    def _required_catalogue_repository(self) -> CourseRepository:
        if self.catalogue_repository is None:
            raise ValueError("catalogue repository is required")
        return self.catalogue_repository

    def _required_attempt_result_repository(self) -> AttemptResultRepository:
        if self.attempt_result_repository is None:
            raise ValueError("attempt result repository is required")
        return self.attempt_result_repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

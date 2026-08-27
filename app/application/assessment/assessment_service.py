from app.application.assessment.assessment_commands import (
    AddQuestionToAssessmentCommand,
    CreateAssessmentCommand,
    GetAssessmentCommand,
    ListAssessmentsCommand,
    PublishAssessmentCommand,
    UpdateAssessmentCommand,
)
from app.application.assessment.assessment_handlers import (
    AddQuestionToAssessmentHandler,
    CreateAssessmentHandler,
    GetAssessmentHandler,
    ListAssessmentsHandler,
    PublishAssessmentHandler,
    UpdateAssessmentHandler,
)
from app.application.common.uow import AssessmentUnitOfWorkFactory
from app.domain.assessment.assessment import Assessment
from app.domain.repositories.assessment import AssessmentRepository
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
        event_bus: EventBus | None = None,
        uow_factory: AssessmentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.question_repository = question_repository
        self.catalogue_repository = catalogue_repository
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
    ) -> Assessment:
        command = CreateAssessmentCommand(
            tenant_id=tenant_id,
            course_id=course_id,
            title=title,
            instructions=instructions,
            duration_minutes=duration_minutes,
            passing_score=passing_score,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await CreateAssessmentHandler(
                    uow.assessments, uow.catalogue
                ).handle(command)
                events = assessment.pull_events()
            self._publish_events(events)
            return assessment
        assessment = await CreateAssessmentHandler(
            self._required_repository(), self._required_catalogue_repository()
        ).handle(command)
        self._publish_events(assessment.pull_events())
        return assessment

    async def get_assessment(
        self, assessment_id: str, tenant_id: str
    ) -> Assessment | None:
        command = GetAssessmentCommand(assessment_id, tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAssessmentHandler(uow.assessments).handle(command)
        return await GetAssessmentHandler(self._required_repository()).handle(command)

    async def list_assessments(
        self, tenant_id: str, course_id: str | None = None
    ) -> list[Assessment]:
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
    ) -> Assessment | None:
        command = UpdateAssessmentCommand(
            assessment_id,
            tenant_id,
            title,
            instructions,
            duration_minutes,
            passing_score,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await UpdateAssessmentHandler(uow.assessments).handle(
                    command
                )
                events = assessment.pull_events() if assessment is not None else []
            self._publish_events(events)
            return assessment
        assessment = await UpdateAssessmentHandler(self._required_repository()).handle(
            command
        )
        if assessment is not None:
            self._publish_events(assessment.pull_events())
        return assessment

    async def publish_assessment(
        self, assessment_id: str, tenant_id: str
    ) -> Assessment | None:
        command = PublishAssessmentCommand(assessment_id, tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await PublishAssessmentHandler(uow.assessments).handle(
                    command
                )
                events = assessment.pull_events() if assessment is not None else []
            self._publish_events(events)
            return assessment
        assessment = await PublishAssessmentHandler(self._required_repository()).handle(
            command
        )
        if assessment is not None:
            self._publish_events(assessment.pull_events())
        return assessment

    async def add_question(
        self, assessment_id: str, question_id: str, tenant_id: str
    ) -> Assessment | None:
        command = AddQuestionToAssessmentCommand(assessment_id, question_id, tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                assessment = await AddQuestionToAssessmentHandler(
                    uow.assessments, uow.questions
                ).handle(command)
                events = assessment.pull_events() if assessment is not None else []
            self._publish_events(events)
            return assessment
        assessment = await AddQuestionToAssessmentHandler(
            self._required_repository(), self._required_question_repository()
        ).handle(command)
        if assessment is not None:
            self._publish_events(assessment.pull_events())
        return assessment

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

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

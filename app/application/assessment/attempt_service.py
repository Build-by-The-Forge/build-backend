from app.application.assessment.attempt_commands import (
    AttemptQuestionSnapshot,
    GetAttemptCommand,
    GetAttemptQuestionsCommand,
    ListMyAttemptsCommand,
    StartAttemptCommand,
    SubmitAttemptCommand,
)
from app.application.assessment.attempt_handlers import (
    GetAttemptHandler,
    GetAttemptQuestionsHandler,
    ListMyAttemptsHandler,
    StartAttemptHandler,
    SubmitAttemptHandler,
)
from app.application.common.uow import AssessmentUnitOfWorkFactory
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class AttemptService:
    def __init__(
        self,
        repository: AttemptRepository | None = None,
        assessment_repository: AssessmentRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: AssessmentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.assessment_repository = assessment_repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def start_attempt(
        self, assessment_id: str, tenant_id: str, user_id: str
    ) -> AssessmentAttempt:
        command = StartAttemptCommand(assessment_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                attempt = await StartAttemptHandler(
                    uow.attempts, uow.assessments
                ).handle(command)
                events = attempt.pull_events()
            self._publish_events(events)
            return attempt
        attempt = await StartAttemptHandler(
            self._required_repository(), self._required_assessment_repository()
        ).handle(command)
        self._publish_events(attempt.pull_events())
        return attempt

    async def get_attempt(
        self, attempt_id: str, tenant_id: str, user_id: str
    ) -> AssessmentAttempt | None:
        command = GetAttemptCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAttemptHandler(uow.attempts).handle(command)
        return await GetAttemptHandler(self._required_repository()).handle(command)

    async def list_my_attempts(
        self, tenant_id: str, user_id: str
    ) -> list[AssessmentAttempt]:
        command = ListMyAttemptsCommand(tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListMyAttemptsHandler(uow.attempts).handle(command)
        return await ListMyAttemptsHandler(self._required_repository()).handle(command)

    async def submit_attempt(
        self, attempt_id: str, tenant_id: str, user_id: str
    ) -> AssessmentAttempt | None:
        command = SubmitAttemptCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                attempt = await SubmitAttemptHandler(uow.attempts).handle(command)
                events = attempt.pull_events() if attempt is not None else []
            self._publish_events(events)
            return attempt
        attempt = await SubmitAttemptHandler(self._required_repository()).handle(
            command
        )
        if attempt is not None:
            self._publish_events(attempt.pull_events())
        return attempt

    async def get_attempt_questions(
        self, attempt_id: str, tenant_id: str, user_id: str
    ) -> list[AttemptQuestionSnapshot] | None:
        command = GetAttemptQuestionsCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAttemptQuestionsHandler(
                    uow.attempts, uow.assessments
                ).handle(command)
        return await GetAttemptQuestionsHandler(
            self._required_repository(), self._required_assessment_repository()
        ).handle(command)

    def _required_repository(self) -> AttemptRepository:
        if self.repository is None:
            raise ValueError("attempt repository is required")
        return self.repository

    def _required_assessment_repository(self) -> AssessmentRepository:
        if self.assessment_repository is None:
            raise ValueError("assessment repository is required")
        return self.assessment_repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

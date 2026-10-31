from app.application.assessment.attempt_commands import (
    AttemptQuestionSnapshot,
    GetAttemptCommand,
    GetAttemptQuestionsCommand,
    GetAttemptResultCommand,
    ListMyAttemptsCommand,
    StartAttemptCommand,
    SubmitAttemptCommand,
)
from app.application.assessment.attempt_handlers import (
    GetAttemptHandler,
    GetAttemptQuestionsHandler,
    GetAttemptResultHandler,
    ListMyAttemptsHandler,
    StartAttemptHandler,
    SubmitAttemptHandler,
)
from app.application.common.uow import AssessmentUnitOfWorkFactory
from app.domain.assessment.attempt import AssessmentAttempt
from app.domain.assessment.errors import AttemptLimitReachedError
from app.domain.assessment.result import AttemptResult
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_result import AttemptResultRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class AttemptService:
    def __init__(
        self,
        repository: AttemptRepository | None = None,
        assessment_repository: AssessmentRepository | None = None,
        result_repository: AttemptResultRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: AssessmentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.assessment_repository = assessment_repository
        self.result_repository = result_repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def start_attempt(self, assessment_id: str, tenant_id: str, user_id: str) -> AssessmentAttempt:
        command = StartAttemptCommand(assessment_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = StartAttemptHandler(uow.attempts, uow.assessments, uow.attempt_answers, uow.attempt_results)
                attempt = await handler.handle(command)
        else:
            handler = StartAttemptHandler(self._required_repository(), self._required_assessment_repository())
            attempt = await handler.handle(command)
        # Raised only now: an expired attempt finalized above stays finalized.
        self._publish_events(handler.finalized_events + (attempt.pull_events() if attempt is not None else []))
        if attempt is None:
            raise AttemptLimitReachedError("ATTEMPT_LIMIT_REACHED")
        return attempt

    async def attempts_used(self, tenant_id: str, user_id: str) -> dict[str, int]:
        """The attempts this user has started, by assessment, finalized or not."""
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await uow.attempts.counts_by_assessment(user_id, tenant_id)
        return await self._required_repository().counts_by_assessment(user_id, tenant_id)

    async def get_attempt(self, attempt_id: str, tenant_id: str, user_id: str) -> AssessmentAttempt | None:
        command = GetAttemptCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAttemptHandler(uow.attempts).handle(command)
        return await GetAttemptHandler(self._required_repository()).handle(command)

    async def list_my_attempts(self, tenant_id: str, user_id: str) -> list[AssessmentAttempt]:
        command = ListMyAttemptsCommand(tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListMyAttemptsHandler(uow.attempts).handle(command)
        return await ListMyAttemptsHandler(self._required_repository()).handle(command)

    async def submit_attempt(self, attempt_id: str, tenant_id: str, user_id: str) -> AssessmentAttempt | None:
        command = SubmitAttemptCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                attempt = await SubmitAttemptHandler(
                    uow.attempts,
                    uow.assessments,
                    uow.attempt_answers,
                    uow.attempt_results,
                ).handle(command)
                events = attempt.pull_events() if attempt is not None else []
            self._publish_events(events)
            return attempt
        attempt = await SubmitAttemptHandler(self._required_repository()).handle(command)
        if attempt is not None:
            self._publish_events(attempt.pull_events())
        return attempt

    async def get_attempt_questions(self, attempt_id: str, tenant_id: str, user_id: str) -> list[AttemptQuestionSnapshot] | None:
        command = GetAttemptQuestionsCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAttemptQuestionsHandler(uow.attempts, uow.assessments).handle(command)
        return await GetAttemptQuestionsHandler(self._required_repository(), self._required_assessment_repository()).handle(
            command
        )

    async def get_attempt_result(
        self,
        attempt_id: str,
        tenant_id: str,
        user_id: str,
        is_staff: bool = False,
    ) -> AttemptResult | None:
        command = GetAttemptResultCommand(
            attempt_id=attempt_id,
            tenant_id=tenant_id,
            user_id=user_id,
            is_staff=is_staff,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAttemptResultHandler(uow.attempts, uow.attempt_results).handle(command)
        return await GetAttemptResultHandler(self._required_repository(), self._required_result_repository()).handle(command)

    def _required_repository(self) -> AttemptRepository:
        if self.repository is None:
            raise ValueError("attempt repository is required")
        return self.repository

    def _required_assessment_repository(self) -> AssessmentRepository:
        if self.assessment_repository is None:
            raise ValueError("assessment repository is required")
        return self.assessment_repository

    def _required_result_repository(self) -> AttemptResultRepository:
        if self.result_repository is None:
            raise ValueError("attempt result repository is required")
        return self.result_repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

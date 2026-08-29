from app.application.assessment.attempt_answer_commands import (
    DeleteAttemptAnswerCommand,
    GetAttemptAnswersCommand,
    SaveAttemptAnswerCommand,
)
from app.application.assessment.attempt_answer_handlers import (
    DeleteAttemptAnswerHandler,
    GetAttemptAnswersHandler,
    SaveAttemptAnswerHandler,
)
from app.application.common.uow import AssessmentUnitOfWorkFactory
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository


class AttemptAnswerService:
    def __init__(
        self,
        repository: AttemptAnswerRepository | None = None,
        attempt_repository: AttemptRepository | None = None,
        assessment_repository: AssessmentRepository | None = None,
        uow_factory: AssessmentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.attempt_repository = attempt_repository
        self.assessment_repository = assessment_repository
        self.uow_factory = uow_factory

    async def save_answer(
        self,
        attempt_id: str,
        assessment_question_id: str,
        selected_option_index: int,
        tenant_id: str,
        user_id: str,
    ) -> AttemptAnswer:
        command = SaveAttemptAnswerCommand(
            attempt_id,
            assessment_question_id,
            selected_option_index,
            tenant_id,
            user_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await SaveAttemptAnswerHandler(
                    uow.attempts, uow.assessments, uow.attempt_answers
                ).handle(command)
        return await SaveAttemptAnswerHandler(
            self._attempts(), self._assessments(), self._answers()
        ).handle(command)

    async def get_answers(
        self, attempt_id: str, tenant_id: str, user_id: str
    ) -> list[AttemptAnswer] | None:
        command = GetAttemptAnswersCommand(attempt_id, tenant_id, user_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAttemptAnswersHandler(
                    uow.attempts, uow.attempt_answers
                ).handle(command)
        return await GetAttemptAnswersHandler(self._attempts(), self._answers()).handle(
            command
        )

    async def delete_answer(
        self, attempt_id: str, assessment_question_id: str, tenant_id: str, user_id: str
    ) -> bool | None:
        command = DeleteAttemptAnswerCommand(
            attempt_id, assessment_question_id, tenant_id, user_id
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await DeleteAttemptAnswerHandler(
                    uow.attempts, uow.attempt_answers
                ).handle(command)
        return await DeleteAttemptAnswerHandler(
            self._attempts(), self._answers()
        ).handle(command)

    def _answers(self) -> AttemptAnswerRepository:
        if self.repository is None:
            raise ValueError("attempt answer repository is required")
        return self.repository

    def _attempts(self) -> AttemptRepository:
        if self.attempt_repository is None:
            raise ValueError("attempt repository is required")
        return self.attempt_repository

    def _assessments(self) -> AssessmentRepository:
        if self.assessment_repository is None:
            raise ValueError("assessment repository is required")
        return self.assessment_repository

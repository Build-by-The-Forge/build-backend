from app.application.assessment.attempt_answer_commands import (
    DeleteAttemptAnswerCommand,
    GetAttemptAnswersCommand,
    SaveAttemptAnswerCommand,
)
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository


class SaveAttemptAnswerHandler:
    def __init__(
        self,
        attempts: AttemptRepository,
        assessments: AssessmentRepository,
        answers: AttemptAnswerRepository,
    ) -> None:
        self.attempts = attempts
        self.assessments = assessments
        self.answers = answers

    async def handle(self, command: SaveAttemptAnswerCommand) -> AttemptAnswer:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None:
            raise LookupError("attempt not found")
        attempt.ensure_answer_mutation_allowed()

        snapshots = await self.assessments.list_question_snapshots(attempt.assessment_id, tenant_id=command.tenant_id)
        snapshot = next(
            (item for item in snapshots if item.assessment_question_id == command.assessment_question_id),
            None,
        )
        if snapshot is None:
            raise LookupError("assessment question not found")
        if command.selected_option_index < 0 or command.selected_option_index >= len(snapshot.options):
            raise ValueError("selected_option_index is outside the valid option range")

        answer = await self.answers.get_by_attempt_and_question(
            command.attempt_id,
            command.assessment_question_id,
            command.tenant_id,
        )
        if answer is None:
            answer = AttemptAnswer.create(
                tenant_id=command.tenant_id,
                attempt_id=command.attempt_id,
                assessment_question_id=command.assessment_question_id,
                selected_option_index=command.selected_option_index,
            )
        else:
            answer.update_selection(command.selected_option_index, option_count=len(snapshot.options))
        return await self.answers.save(answer)


class GetAttemptAnswersHandler:
    def __init__(self, attempts: AttemptRepository, answers: AttemptAnswerRepository) -> None:
        self.attempts = attempts
        self.answers = answers

    async def handle(self, command: GetAttemptAnswersCommand) -> list[AttemptAnswer] | None:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None:
            return None
        return await self.answers.list_by_attempt(command.attempt_id, command.tenant_id)


class DeleteAttemptAnswerHandler:
    def __init__(self, attempts: AttemptRepository, answers: AttemptAnswerRepository) -> None:
        self.attempts = attempts
        self.answers = answers

    async def handle(self, command: DeleteAttemptAnswerCommand) -> bool | None:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None:
            return None
        attempt.ensure_answer_mutation_allowed()
        answer = await self.answers.get_by_attempt_and_question(
            command.attempt_id,
            command.assessment_question_id,
            command.tenant_id,
        )
        if answer is None:
            return False
        await self.answers.delete(answer)
        return True

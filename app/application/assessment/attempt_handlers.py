from app.application.assessment.attempt_commands import (
    AttemptQuestionSnapshot,
    GetAttemptCommand,
    GetAttemptQuestionsCommand,
    GetAttemptResultCommand,
    ListMyAttemptsCommand,
    StartAttemptCommand,
    SubmitAttemptCommand,
)
from app.domain.assessment.assessment import AssessmentStatus
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.result import AttemptResult
from app.domain.assessment.scoring import AssessmentScorer
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository
from app.domain.repositories.attempt_result import AttemptResultRepository


class StartAttemptHandler:
    def __init__(
        self,
        attempts: AttemptRepository,
        assessments: AssessmentRepository,
    ) -> None:
        self.attempts = attempts
        self.assessments = assessments

    async def handle(self, command: StartAttemptCommand) -> AssessmentAttempt:
        assessment = await self.assessments.get_by_id(
            command.assessment_id, tenant_id=command.tenant_id
        )
        if assessment is None:
            raise ValueError("assessment not found")
        if assessment.status != AssessmentStatus.PUBLISHED:
            raise ValueError("assessment is not available for attempts")

        active = await self.attempts.get_active_for_user(
            command.assessment_id, command.user_id, command.tenant_id
        )
        if active is not None:
            return active

        attempt = AssessmentAttempt.start(
            tenant_id=command.tenant_id,
            assessment_id=command.assessment_id,
            user_id=command.user_id,
        )
        return await self.attempts.save(attempt, tenant_id=command.tenant_id)


class GetAttemptHandler:
    def __init__(self, repository: AttemptRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetAttemptCommand) -> AssessmentAttempt | None:
        return await self.repository.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )


class ListMyAttemptsHandler:
    def __init__(self, repository: AttemptRepository) -> None:
        self.repository = repository

    async def handle(self, command: ListMyAttemptsCommand) -> list[AssessmentAttempt]:
        return await self.repository.list_by_user(
            command.user_id, tenant_id=command.tenant_id
        )


class SubmitAttemptHandler:
    def __init__(
        self,
        repository: AttemptRepository,
        assessments: AssessmentRepository | None = None,
        answers: AttemptAnswerRepository | None = None,
        results: AttemptResultRepository | None = None,
    ) -> None:
        self.repository = repository
        self.assessments = assessments
        self.answers = answers
        self.results = results

    async def handle(self, command: SubmitAttemptCommand) -> AssessmentAttempt | None:
        attempt = await self.repository.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None:
            return None
        attempt.submit()

        if (
            self.assessments is not None
            and self.answers is not None
            and self.results is not None
        ):
            assessment = await self.assessments.get_by_id(
                attempt.assessment_id, tenant_id=command.tenant_id
            )
            if assessment is None:
                raise ValueError("assessment not found")
            questions = await self.assessments.list_question_snapshots(
                attempt.assessment_id, tenant_id=command.tenant_id
            )
            learner_answers = await self.answers.list_by_attempt(
                command.attempt_id, tenant_id=command.tenant_id
            )
            result = AssessmentScorer.score(
                attempt=attempt,
                assessment=assessment,
                questions=questions,
                answers=learner_answers,
            )
            await self.results.save(result)
            attempt._events.extend(result.pull_events())

        return await self.repository.update(attempt, tenant_id=command.tenant_id)


class GetAttemptQuestionsHandler:
    def __init__(
        self,
        attempts: AttemptRepository,
        assessments: AssessmentRepository,
    ) -> None:
        self.attempts = attempts
        self.assessments = assessments

    async def handle(
        self, command: GetAttemptQuestionsCommand
    ) -> list[AttemptQuestionSnapshot] | None:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None or attempt.status != AttemptStatus.IN_PROGRESS:
            return None

        snapshots = await self.assessments.list_question_snapshots(
            attempt.assessment_id, tenant_id=command.tenant_id
        )
        return [
            AttemptQuestionSnapshot(
                assessment_question_id=question.assessment_question_id
                or question.question_id,
                question_id=question.question_id,
                sequence=sequence,
                prompt=question.prompt,
                options=list(question.options),
                marks=question.marks,
            )
            for sequence, question in enumerate(snapshots)
        ]


class GetAttemptResultHandler:
    def __init__(
        self,
        attempts: AttemptRepository,
        results: AttemptResultRepository,
    ) -> None:
        self.attempts = attempts
        self.results = results

    async def handle(self, command: GetAttemptResultCommand) -> AttemptResult | None:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=None if command.is_staff else command.user_id,
        )
        if attempt is None:
            return None
        if attempt.status != AttemptStatus.SUBMITTED:
            raise ValueError("attempt is not submitted")
        return await self.results.get_by_attempt_id(
            command.attempt_id, tenant_id=command.tenant_id
        )

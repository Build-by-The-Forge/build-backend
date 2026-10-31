from dataclasses import dataclass

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
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus, FinalizedBy
from app.domain.assessment.errors import ResultNotReleasedError
from app.domain.assessment.result import AttemptResult
from app.domain.assessment.result_disclosure import disclose
from app.domain.assessment.scoring import AssessmentScorer
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository
from app.domain.repositories.attempt_result import AttemptResultRepository, ResultReleaseRepository
from app.events.base import DomainEvent


@dataclass(frozen=True, slots=True)
class ReadableResult:
    result: AttemptResult
    feedback_shown: bool


async def finalize_attempt(
    attempts: AttemptRepository,
    assessments: AssessmentRepository | None,
    answers: AttemptAnswerRepository | None,
    results: AttemptResultRepository | None,
    *,
    attempt_id: str,
    tenant_id: str,
    user_id: str,
    finalized_by: FinalizedBy = FinalizedBy.STUDENT,
) -> AssessmentAttempt | None:
    """The one path that makes an attempt final: student submit, a start, a
    read and the worker all come here. Unanswered questions score zero."""
    # The lock makes concurrent calls take turns: one grades, the rest find it
    # submitted and return it unchanged.
    attempt = await attempts.get_by_id_for_update(attempt_id, tenant_id=tenant_id, user_id=user_id)
    if attempt is None:
        return None
    if attempt.status == AttemptStatus.SUBMITTED:
        attempt.newly_submitted = False
        return attempt
    attempt.submit(now=await attempts.database_now(), finalized_by=finalized_by)

    if assessments is not None and answers is not None and results is not None:
        assessment = await assessments.get_by_id(attempt.assessment_id, tenant_id=tenant_id)
        if assessment is None:
            raise ValueError("assessment not found")
        questions = await assessments.list_question_snapshots(attempt.assessment_id, tenant_id=tenant_id)
        learner_answers = await answers.list_by_attempt(attempt_id, tenant_id=tenant_id)
        result = AssessmentScorer.score(
            attempt=attempt,
            assessment=assessment,
            questions=questions,
            answers=learner_answers,
        )
        await results.save(result)
        attempt._events.extend(result.pull_events())

    return await attempts.update(attempt, tenant_id=tenant_id)


async def finalize_if_expired(
    attempt: AssessmentAttempt,
    attempts: AttemptRepository,
    assessments: AssessmentRepository | None,
    answers: AttemptAnswerRepository | None,
    results: AttemptResultRepository | None,
) -> AssessmentAttempt:
    """The fallback for when no worker has run: a read never shows an expired
    attempt as in progress. Its deadline never moves, so the check needs no lock;
    finalize_attempt takes it, and copes with anyone who finalized in between."""
    if attempt.status != AttemptStatus.IN_PROGRESS or assessments is None or answers is None or results is None:
        return attempt
    if not attempt.is_expired(await attempts.database_now()):
        return attempt
    finalized = await finalize_attempt(
        attempts,
        assessments,
        answers,
        results,
        attempt_id=attempt.id,
        tenant_id=attempt.tenant_id,
        user_id=attempt.user_id,
        finalized_by=FinalizedBy.DEADLINE,
    )
    return finalized or attempt


class StartAttemptHandler:
    def __init__(
        self,
        attempts: AttemptRepository,
        assessments: AssessmentRepository,
        answers: AttemptAnswerRepository | None = None,
        results: AttemptResultRepository | None = None,
    ) -> None:
        self.attempts = attempts
        self.assessments = assessments
        self.answers = answers
        self.results = results
        # From an expired attempt this start finalized, for the caller to publish.
        self.finalized_events: list[DomainEvent] = []

    async def handle(self, command: StartAttemptCommand) -> AssessmentAttempt | None:
        """The attempt, or None if the policy's limit is reached. Not an
        exception: the unit of work must still commit an expired attempt this
        call finalized."""
        assessment = await self.assessments.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            raise ValueError("assessment not found")
        if assessment.status != AssessmentStatus.PUBLISHED:
            raise ValueError("assessment is not available for attempts")

        # What protects the limit. Without it a slow start can count attempts,
        # then wait while a faster one starts and submits: nothing is in
        # progress any more, so the unique index lets the stale count through.
        await self.attempts.lock_starts(command.assessment_id, command.user_id, command.tenant_id)

        active = await self.attempts.get_active_for_user(command.assessment_id, command.user_id, command.tenant_id)
        if active is not None:
            finalized = await finalize_if_expired(active, self.attempts, self.assessments, self.answers, self.results)
            if finalized.status == AttemptStatus.IN_PROGRESS:
                return finalized
            self.finalized_events = finalized.pull_events()

        used = await self.attempts.count_for_user(command.assessment_id, command.user_id, command.tenant_id)
        if not assessment.attempt_policy.allows_new_attempt(used):
            return None

        attempt = AssessmentAttempt.start(
            tenant_id=command.tenant_id,
            assessment_id=command.assessment_id,
            user_id=command.user_id,
            duration_minutes=assessment.duration_minutes,
            now=await self.attempts.database_now(),
        )
        if await self.attempts.insert_unless_active(attempt):
            return attempt
        # A path without the lock got there first.
        existing = await self.attempts.get_active_for_user(command.assessment_id, command.user_id, command.tenant_id)
        if existing is None:
            raise ValueError("assessment is not available for attempts")
        return existing


class GetAttemptHandler:
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

    async def handle(self, command: GetAttemptCommand) -> AssessmentAttempt | None:
        attempt = await self.repository.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None:
            return None
        return await finalize_if_expired(attempt, self.repository, self.assessments, self.answers, self.results)


class ListMyAttemptsHandler:
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

    async def handle(self, command: ListMyAttemptsCommand) -> list[AssessmentAttempt]:
        attempts = await self.repository.list_by_user(command.user_id, tenant_id=command.tenant_id)
        return [
            await finalize_if_expired(attempt, self.repository, self.assessments, self.answers, self.results)
            for attempt in attempts
        ]


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
        return await finalize_attempt(
            self.repository,
            self.assessments,
            self.answers,
            self.results,
            attempt_id=command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )


class GetAttemptQuestionsHandler:
    def __init__(
        self,
        attempts: AttemptRepository,
        assessments: AssessmentRepository,
        answers: AttemptAnswerRepository | None = None,
        results: AttemptResultRepository | None = None,
    ) -> None:
        self.attempts = attempts
        self.assessments = assessments
        self.answers = answers
        self.results = results
        self.finalized_events: list[DomainEvent] = []

    async def handle(self, command: GetAttemptQuestionsCommand) -> list[AttemptQuestionSnapshot] | None:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=command.user_id,
        )
        if attempt is None:
            return None
        attempt = await finalize_if_expired(attempt, self.attempts, self.assessments, self.answers, self.results)
        self.finalized_events = attempt.pull_events()
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return None

        snapshots = await self.assessments.list_question_snapshots(attempt.assessment_id, tenant_id=command.tenant_id)
        return [
            AttemptQuestionSnapshot(
                assessment_question_id=question.assessment_question_id or question.question_id,
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
        assessments: AssessmentRepository,
        releases: ResultReleaseRepository,
        answers: AttemptAnswerRepository | None = None,
    ) -> None:
        self.attempts = attempts
        self.results = results
        self.assessments = assessments
        self.releases = releases
        self.answers = answers
        self.finalized_events: list[DomainEvent] = []

    async def _finalize_if_expired(self, attempt: AssessmentAttempt) -> AssessmentAttempt:
        finalized = await finalize_if_expired(attempt, self.attempts, self.assessments, self.answers, self.results)
        self.finalized_events.extend(finalized.pull_events())
        return finalized

    async def handle(self, command: GetAttemptResultCommand) -> ReadableResult | None:
        attempt = await self.attempts.get_by_id(
            command.attempt_id,
            tenant_id=command.tenant_id,
            user_id=None if command.is_staff else command.user_id,
        )
        if attempt is None:
            return None
        attempt = await self._finalize_if_expired(attempt)
        if attempt.status != AttemptStatus.SUBMITTED:
            raise ValueError("attempt is not submitted")

        result = await self.results.get_by_attempt_id(command.attempt_id, tenant_id=command.tenant_id)
        if result is None:
            return None
        if command.is_staff:
            return ReadableResult(result, feedback_shown=True)

        assessment = await self.assessments.get_by_id(attempt.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        released = await self.releases.get(attempt.assessment_id, command.tenant_id)
        used = await self.attempts.count_for_user(attempt.assessment_id, attempt.user_id, command.tenant_id)
        active = await self.attempts.get_active_for_user(attempt.assessment_id, attempt.user_id, command.tenant_id)
        if active is not None:
            active = await self._finalize_if_expired(active)
        disclosure = disclose(
            assessment.attempt_policy,
            finalized=True,
            released=released is not None,
            attempts_used=used,
            all_finalized=active is None or active.status == AttemptStatus.SUBMITTED,
        )
        if not disclosure.result_visible:
            raise ResultNotReleasedError("RESULT_NOT_RELEASED")
        return ReadableResult(result, feedback_shown=disclosure.feedback_shown)

from datetime import datetime, timezone

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
from app.domain.assessment.assessment import Assessment, AssessmentStatus
from app.domain.assessment.result import AttemptResult
from app.domain.assessment.result_disclosure import standing_attempts
from app.domain.assessment.result_release import ResultRelease
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt_result import AttemptResultRepository, ResultReleaseRepository
from app.domain.repositories.course import CourseRepository
from app.domain.repositories.question import QuestionRepository


class CreateAssessmentHandler:
    def __init__(
        self,
        repository: AssessmentRepository,
        catalogue_repository: CourseRepository,
    ) -> None:
        self.repository = repository
        self.catalogue_repository = catalogue_repository

    async def handle(self, command: CreateAssessmentCommand) -> Assessment:
        course = await self.catalogue_repository.get_by_id(command.course_id, tenant_id=command.tenant_id)
        if course is None:
            raise ValueError("course not found")
        assessment = Assessment.create(
            tenant_id=command.tenant_id,
            course_id=command.course_id,
            title=command.title,
            instructions=command.instructions,
            duration_minutes=command.duration_minutes,
            passing_score=command.passing_score,
            attempt_policy=command.attempt_policy,
        )
        return await self.repository.save(assessment, tenant_id=command.tenant_id)


class GetAssessmentHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetAssessmentCommand) -> Assessment | None:
        return await self.repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)


class ListAssessmentsHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: ListAssessmentsCommand) -> list[Assessment]:
        if command.course_id is not None:
            return await self.repository.list_by_course(command.course_id, tenant_id=command.tenant_id)
        return await self.repository.list_all(tenant_id=command.tenant_id)


class UpdateAssessmentHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateAssessmentCommand) -> Assessment | None:
        # With publish taking the same lock, an edit can't read a draft and
        # write its policy after the assessment was published.
        await self.repository.lock_for_change(command.assessment_id, command.tenant_id)
        assessment = await self.repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        assessment.update_details(
            title=command.title,
            instructions=command.instructions,
            duration_minutes=command.duration_minutes,
            passing_score=command.passing_score,
            attempt_policy=command.attempt_policy,
        )
        return await self.repository.update(assessment, tenant_id=command.tenant_id)


class PublishAssessmentHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: PublishAssessmentCommand) -> Assessment | None:
        await self.repository.lock_for_change(command.assessment_id, command.tenant_id)
        assessment = await self.repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        assessment.publish()
        return await self.repository.update(assessment, tenant_id=command.tenant_id)


class AddQuestionToAssessmentHandler:
    def __init__(
        self,
        repository: AssessmentRepository,
        question_repository: QuestionRepository,
    ) -> None:
        self.repository = repository
        self.question_repository = question_repository

    async def handle(self, command: AddQuestionToAssessmentCommand) -> Assessment | None:
        assessment = await self.repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        question = await self.question_repository.get_by_id(command.question_id, tenant_id=command.tenant_id)
        if question is None:
            raise ValueError("question not found")
        correct_idx = next(
            (index for index, option in enumerate(question.options) if option.is_correct),
            0,
        )
        assessment.add_question(
            question_id=question.id.value,
            prompt=question.prompt.value,
            options=[option.text.value for option in question.options],
            marks=question.marks.value,
            correct_option_index=correct_idx,
        )
        return await self.repository.update(assessment, tenant_id=command.tenant_id)


class ReleaseResultsHandler:
    def __init__(self, assessments: AssessmentRepository, releases: ResultReleaseRepository) -> None:
        self.assessments = assessments
        self.releases = releases

    async def handle(self, command: ReleaseResultsCommand) -> tuple[ResultRelease, bool] | None:
        """The release, and whether this call made it. A repeat returns the first."""
        assessment = await self.assessments.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        if assessment.status == AssessmentStatus.DRAFT:
            raise ValueError("a draft has no results to release")
        release = ResultRelease(command.assessment_id, command.tenant_id, command.released_by, datetime.now(timezone.utc))
        created = await self.releases.insert_if_absent(release)
        stored = await self.releases.get(command.assessment_id, command.tenant_id)
        if stored is None:
            raise ValueError("assessment not found")
        return stored, created


class GetAssessmentResultsHandler:
    def __init__(
        self,
        assessment_repository: AssessmentRepository,
        attempt_result_repository: AttemptResultRepository,
    ) -> None:
        self.assessment_repository = assessment_repository
        self.attempt_result_repository = attempt_result_repository

    async def handle(self, command: GetAssessmentResultsCommand) -> tuple[list[AttemptResult], int] | None:
        assessment = await self.assessment_repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        return await self.attempt_result_repository.list_by_assessment(
            assessment_id=command.assessment_id,
            tenant_id=command.tenant_id,
            limit=command.limit,
            offset=command.offset,
        )

    async def standing(self, command: GetAssessmentResultsCommand) -> set[str]:
        """The attempt that stands for each student, across every result."""
        assessment = await self.assessment_repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return set()
        outcomes = await self.attempt_result_repository.list_outcomes(command.assessment_id, command.tenant_id)
        return standing_attempts(assessment.attempt_policy.scoring_policy, outcomes)

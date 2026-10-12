from app.application.assessment.assessment_commands import (
    AddQuestionToAssessmentCommand,
    CreateAssessmentCommand,
    GetAssessmentCommand,
    GetAssessmentResultsCommand,
    ListAssessmentsCommand,
    PublishAssessmentCommand,
    UpdateAssessmentCommand,
)
from app.domain.assessment.assessment import Assessment
from app.domain.assessment.result import AttemptResult
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt_result import AttemptResultRepository
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
        assessment = await self.repository.get_by_id(command.assessment_id, tenant_id=command.tenant_id)
        if assessment is None:
            return None
        assessment.update_details(
            title=command.title,
            instructions=command.instructions,
            duration_minutes=command.duration_minutes,
            passing_score=command.passing_score,
        )
        return await self.repository.update(assessment, tenant_id=command.tenant_id)


class PublishAssessmentHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: PublishAssessmentCommand) -> Assessment | None:
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

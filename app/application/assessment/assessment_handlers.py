from app.application.assessment.assessment_commands import (
    AddQuestionToAssessmentCommand,
    CreateAssessmentCommand,
    GetAssessmentCommand,
    ListAssessmentsCommand,
    PublishAssessmentCommand,
    UpdateAssessmentCommand,
)
from app.domain.assessment.assessment import Assessment
from app.domain.repositories.assessment import AssessmentRepository
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
        course = await self.catalogue_repository.get_by_id(
            command.course_id, tenant_id=command.tenant_id
        )
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
        return await self.repository.get_by_id(
            command.assessment_id, tenant_id=command.tenant_id
        )


class ListAssessmentsHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: ListAssessmentsCommand) -> list[Assessment]:
        if command.course_id is not None:
            return await self.repository.list_by_course(
                command.course_id, tenant_id=command.tenant_id
            )
        return await self.repository.list_all(tenant_id=command.tenant_id)


class UpdateAssessmentHandler:
    def __init__(self, repository: AssessmentRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateAssessmentCommand) -> Assessment | None:
        assessment = await self.repository.get_by_id(
            command.assessment_id, tenant_id=command.tenant_id
        )
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
        assessment = await self.repository.get_by_id(
            command.assessment_id, tenant_id=command.tenant_id
        )
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

    async def handle(
        self, command: AddQuestionToAssessmentCommand
    ) -> Assessment | None:
        assessment = await self.repository.get_by_id(
            command.assessment_id, tenant_id=command.tenant_id
        )
        if assessment is None:
            return None
        question = await self.question_repository.get_by_id(
            command.question_id, tenant_id=command.tenant_id
        )
        if question is None:
            raise ValueError("question not found")
        assessment.add_question(
            question_id=question.id.value,
            prompt=question.prompt.value,
            options=[option.text.value for option in question.options],
            marks=question.marks.value,
        )
        return await self.repository.update(assessment, tenant_id=command.tenant_id)

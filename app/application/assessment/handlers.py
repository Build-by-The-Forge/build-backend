from app.application.assessment.commands import (
    ArchiveQuestionCommand,
    CreateQuestionCommand,
    GetQuestionCommand,
    ListQuestionsByLearningOutcomeCommand,
    ListQuestionsByTopicCommand,
    PublishQuestionCommand,
    UpdateQuestionCommand,
)
from app.domain.assessment.question import Question, QuestionOption
from app.domain.assessment.value_objects import (
    Difficulty,
    QuestionDisplayOrder,
    QuestionExplanation,
    QuestionId,
    QuestionMarks,
    QuestionOptionId,
    QuestionOptionText,
    QuestionPrompt,
    QuestionType,
)
from app.domain.repositories.question import QuestionRepository


class CreateQuestionHandler:
    def __init__(
        self,
        repository: QuestionRepository,
        catalogue_repository: object,
    ) -> None:
        self.repository = repository
        self.catalogue_repository = catalogue_repository

    async def handle(self, command: CreateQuestionCommand) -> Question | None:
        topic = await self.catalogue_repository.get_by_topic_id(
            command.topic_id, tenant_id=command.tenant_id
        )
        if topic is None:
            return None

        if command.learning_outcome_id is not None:
            outcome_course = await self.catalogue_repository.get_by_learning_outcome_id(
                command.learning_outcome_id, tenant_id=command.tenant_id
            )
            if outcome_course is None:
                return None
            topic_found = any(
                topic.id.value == command.topic_id for topic in outcome_course.topics
            )
            if not topic_found:
                return None

        options = []
        for raw_option in command.options or []:
            option_text = raw_option.get("text")
            display_order = raw_option.get("display_order")
            is_correct = bool(raw_option.get("is_correct", False))
            if option_text is None or display_order is None:
                continue
            options.append(
                QuestionOption(
                    id=QuestionOptionId(""),
                    question_id=QuestionId(""),
                    text=QuestionOptionText(str(option_text)),
                    display_order=QuestionDisplayOrder(int(display_order)),
                    is_correct=is_correct,
                )
            )

        question = Question.create(
            tenant_id=command.tenant_id or "",
            topic_id=command.topic_id,
            learning_outcome_id=command.learning_outcome_id,
            question_type=QuestionType(command.question_type),
            prompt=QuestionPrompt(command.prompt),
            explanation=(
                QuestionExplanation(command.explanation)
                if command.explanation is not None
                else None
            ),
            difficulty=Difficulty(command.difficulty),
            marks=QuestionMarks(command.marks),
            options=options,
        )
        return await self.repository.save(question, tenant_id=command.tenant_id)


class UpdateQuestionHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateQuestionCommand) -> Question | None:
        question = await self.repository.get_by_id(
            command.question_id,
            tenant_id=command.tenant_id,
        )
        if question is None:
            return None
        question.update_details(
            prompt=QuestionPrompt(command.prompt) if command.prompt is not None else None,
            explanation=(
                QuestionExplanation(command.explanation)
                if command.explanation is not None
                else None
            ),
            difficulty=Difficulty(command.difficulty) if command.difficulty is not None else None,
            marks=QuestionMarks(command.marks) if command.marks is not None else None,
        )
        return await self.repository.update(question, tenant_id=command.tenant_id)


class PublishQuestionHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(self, command: PublishQuestionCommand) -> Question | None:
        question = await self.repository.get_by_id(
            command.question_id,
            tenant_id=command.tenant_id,
        )
        if question is None:
            return None
        question.publish()
        return await self.repository.update(question, tenant_id=command.tenant_id)


class ArchiveQuestionHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(self, command: ArchiveQuestionCommand) -> Question | None:
        question = await self.repository.get_by_id(
            command.question_id,
            tenant_id=command.tenant_id,
        )
        if question is None:
            return None
        question.archive()
        return await self.repository.update(question, tenant_id=command.tenant_id)


class GetQuestionHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(self, command: GetQuestionCommand) -> Question | None:
        return await self.repository.get_by_id(
            command.question_id,
            tenant_id=command.tenant_id,
        )


class ListQuestionsByTopicHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(self, command: ListQuestionsByTopicCommand) -> list[Question]:
        return await self.repository.list_by_topic(
            command.topic_id,
            tenant_id=command.tenant_id,
        )


class ListQuestionsByLearningOutcomeHandler:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: ListQuestionsByLearningOutcomeCommand
    ) -> list[Question]:
        return await self.repository.list_by_learning_outcome(
            command.learning_outcome_id,
            tenant_id=command.tenant_id,
        )

from app.application.assessment.commands import (
    ArchiveQuestionCommand,
    CreateQuestionCommand,
    GetQuestionCommand,
    ListQuestionsByLearningOutcomeCommand,
    ListQuestionsByTopicCommand,
    PublishQuestionCommand,
    UpdateQuestionCommand,
)
from app.application.assessment.handlers import (
    ArchiveQuestionHandler,
    CreateQuestionHandler,
    GetQuestionHandler,
    ListQuestionsByLearningOutcomeHandler,
    ListQuestionsByTopicHandler,
    PublishQuestionHandler,
    UpdateQuestionHandler,
)
from app.application.common.uow import AssessmentUnitOfWorkFactory
from app.domain.assessment.question import Question
from app.domain.repositories.course import CourseRepository
from app.domain.repositories.question import QuestionRepository
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class QuestionService:
    def __init__(
        self,
        repository: QuestionRepository | None = None,
        catalogue_repository: CourseRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: AssessmentUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.catalogue_repository = catalogue_repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def create_question(
        self,
        topic_id: str,
        question_type: str,
        prompt: str,
        difficulty: str = "medium",
        marks: int = 1,
        explanation: str | None = None,
        learning_outcome_id: str | None = None,
        options: list[dict[str, object]] | None = None,
        tenant_id: str | None = None,
    ) -> Question | None:
        command = CreateQuestionCommand(
            topic_id=topic_id,
            question_type=question_type,
            prompt=prompt,
            difficulty=difficulty,
            marks=marks,
            explanation=explanation,
            learning_outcome_id=learning_outcome_id,
            options=options,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = CreateQuestionHandler(
                    repository=uow.questions,
                    catalogue_repository=uow.catalogue,
                )
                question = await handler.handle(command)
                if question is not None:
                    self._publish_events(question.pull_events())
                return question

        if self.repository is None or self.catalogue_repository is None:
            raise ValueError("repository and catalogue_repository are required")

        handler = CreateQuestionHandler(
            repository=self.repository,
            catalogue_repository=self.catalogue_repository,
        )
        question = await handler.handle(command)
        if question is not None:
            self._publish_events(question.pull_events())
        return question

    async def update_question(
        self,
        question_id: str,
        tenant_id: str | None = None,
        prompt: str | None = None,
        explanation: str | None = None,
        difficulty: str | None = None,
        marks: int | None = None,
    ) -> Question | None:
        command = UpdateQuestionCommand(
            question_id=question_id,
            prompt=prompt,
            explanation=explanation,
            difficulty=difficulty,
            marks=marks,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = UpdateQuestionHandler(repository=uow.questions)
                question = await handler.handle(command)
                if question is not None:
                    self._publish_events(question.pull_events())
                return question

        if self.repository is None:
            raise ValueError("repository is required")

        handler = UpdateQuestionHandler(repository=self.repository)
        question = await handler.handle(command)
        if question is not None:
            self._publish_events(question.pull_events())
        return question

    async def publish_question(
        self,
        question_id: str,
        tenant_id: str | None = None,
    ) -> Question | None:
        command = PublishQuestionCommand(question_id=question_id, tenant_id=tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = PublishQuestionHandler(repository=uow.questions)
                question = await handler.handle(command)
                if question is not None:
                    self._publish_events(question.pull_events())
                return question

        if self.repository is None:
            raise ValueError("repository is required")

        handler = PublishQuestionHandler(repository=self.repository)
        question = await handler.handle(command)
        if question is not None:
            self._publish_events(question.pull_events())
        return question

    async def archive_question(
        self,
        question_id: str,
        tenant_id: str | None = None,
    ) -> Question | None:
        command = ArchiveQuestionCommand(question_id=question_id, tenant_id=tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ArchiveQuestionHandler(repository=uow.questions)
                question = await handler.handle(command)
                if question is not None:
                    self._publish_events(question.pull_events())
                return question

        if self.repository is None:
            raise ValueError("repository is required")

        handler = ArchiveQuestionHandler(repository=self.repository)
        question = await handler.handle(command)
        if question is not None:
            self._publish_events(question.pull_events())
        return question

    async def get_question(
        self,
        question_id: str,
        tenant_id: str | None = None,
    ) -> Question | None:
        command = GetQuestionCommand(question_id=question_id, tenant_id=tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = GetQuestionHandler(repository=uow.questions)
                return await handler.handle(command)

        if self.repository is None:
            raise ValueError("repository is required")

        handler = GetQuestionHandler(repository=self.repository)
        return await handler.handle(command)

    async def list_questions_by_topic(
        self,
        topic_id: str,
        tenant_id: str | None = None,
    ) -> list[Question]:
        command = ListQuestionsByTopicCommand(topic_id=topic_id, tenant_id=tenant_id)
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ListQuestionsByTopicHandler(repository=uow.questions)
                return await handler.handle(command)

        if self.repository is None:
            raise ValueError("repository is required")

        handler = ListQuestionsByTopicHandler(repository=self.repository)
        return await handler.handle(command)

    async def list_questions_by_learning_outcome(
        self,
        learning_outcome_id: str,
        tenant_id: str | None = None,
    ) -> list[Question]:
        command = ListQuestionsByLearningOutcomeCommand(
            learning_outcome_id=learning_outcome_id,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ListQuestionsByLearningOutcomeHandler(repository=uow.questions)
                return await handler.handle(command)

        if self.repository is None:
            raise ValueError("repository is required")

        handler = ListQuestionsByLearningOutcomeHandler(repository=self.repository)
        return await handler.handle(command)

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

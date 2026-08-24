from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.assessment.question import Question
from app.domain.repositories.question import QuestionRepository
from app.infrastructure.assessment.mappers import (
    question_model_to_domain,
    question_to_model,
)
from app.infrastructure.db.models.assessment import QuestionModel, QuestionOptionModel


class SqlAlchemyQuestionRepository(QuestionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, question: Question, tenant_id: str | None = None) -> Question:
        statement = select(QuestionModel).where(QuestionModel.id == question.id.value)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(QuestionModel.options)
        )
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            model = question_to_model(question)
            if tenant_id is not None:
                model.tenant_id = tenant_id
            self._session.add(model)
        else:
            question_to_model(question, model=model)
            if tenant_id is not None:
                model.tenant_id = tenant_id
        await self._session.flush()
        return question

    async def get_by_id(self, question_id: str, tenant_id: str | None = None) -> Question | None:
        statement = select(QuestionModel).where(QuestionModel.id == question_id)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(QuestionModel.options)
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return question_model_to_domain(model) if model is not None else None

    async def list_by_topic(self, topic_id: str, tenant_id: str | None = None) -> list[Question]:
        statement = select(QuestionModel).where(QuestionModel.topic_id == topic_id)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(QuestionModel.options)
        )
        result = await self._session.scalars(statement)
        return [question_model_to_domain(q) for q in result.all()]

    async def list_by_learning_outcome(
        self, learning_outcome_id: str, tenant_id: str | None = None
    ) -> list[Question]:
        statement = select(QuestionModel).where(QuestionModel.learning_outcome_id == learning_outcome_id)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(QuestionModel.options)
        )
        result = await self._session.scalars(statement)
        return [question_model_to_domain(q) for q in result.all()]

    async def list_all(self, tenant_id: str | None = None) -> list[Question]:
        statement = select(QuestionModel)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(QuestionModel.options)
        )
        result = await self._session.scalars(statement)
        return [question_model_to_domain(q) for q in result.all()]

    async def update(self, question: Question, tenant_id: str | None = None) -> Question:
        statement = select(QuestionModel).where(QuestionModel.id == question.id.value)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(QuestionModel.options)
        )
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            raise ValueError(f"question {question.id.value} not found")
        question_to_model(question, model=model)
        await self._session.flush()
        return question

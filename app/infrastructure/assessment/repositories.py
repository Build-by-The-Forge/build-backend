from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.assessment.assessment import Assessment
from app.domain.assessment.question import Question
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.question import QuestionRepository
from app.infrastructure.assessment.mappers import (
    assessment_model_to_domain,
    assessment_to_model,
    question_model_to_domain,
    question_to_model,
)
from app.infrastructure.db.models.assessment import AssessmentModel, QuestionModel


class SqlAlchemyQuestionRepository(QuestionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, question: Question, tenant_id: str | None = None) -> Question:
        statement = select(QuestionModel).where(QuestionModel.id == question.id.value)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(QuestionModel.options))
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

    async def get_by_id(
        self, question_id: str, tenant_id: str | None = None
    ) -> Question | None:
        statement = select(QuestionModel).where(QuestionModel.id == question_id)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(QuestionModel.options))
        result = await self._session.scalars(statement)
        model = result.first()
        return question_model_to_domain(model) if model is not None else None

    async def list_by_topic(
        self, topic_id: str, tenant_id: str | None = None
    ) -> list[Question]:
        statement = select(QuestionModel).where(QuestionModel.topic_id == topic_id)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(QuestionModel.options))
        result = await self._session.scalars(statement)
        return [question_model_to_domain(q) for q in result.all()]

    async def list_by_learning_outcome(
        self, learning_outcome_id: str, tenant_id: str | None = None
    ) -> list[Question]:
        statement = select(QuestionModel).where(
            QuestionModel.learning_outcome_id == learning_outcome_id
        )
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(QuestionModel.options))
        result = await self._session.scalars(statement)
        return [question_model_to_domain(q) for q in result.all()]

    async def list_all(self, tenant_id: str | None = None) -> list[Question]:
        statement = select(QuestionModel)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(QuestionModel.options))
        result = await self._session.scalars(statement)
        return [question_model_to_domain(q) for q in result.all()]

    async def update(
        self, question: Question, tenant_id: str | None = None
    ) -> Question:
        statement = select(QuestionModel).where(QuestionModel.id == question.id.value)
        if tenant_id is not None:
            statement = statement.where(QuestionModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(QuestionModel.options))
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            raise ValueError(f"question {question.id.value} not found")
        question_to_model(question, model=model)
        await self._session.flush()
        return question


class SqlAlchemyAssessmentRepository(AssessmentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self, assessment: Assessment, tenant_id: str | None = None
    ) -> Assessment:
        statement = select(AssessmentModel).where(AssessmentModel.id == assessment.id)
        if tenant_id is not None:
            statement = statement.where(AssessmentModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(AssessmentModel.questions))
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            model = assessment_to_model(assessment)
            if tenant_id is not None:
                model.tenant_id = tenant_id
            self._session.add(model)
        else:
            assessment_to_model(assessment, model=model)
            if tenant_id is not None:
                model.tenant_id = tenant_id
        await self._session.flush()
        return assessment

    async def get_by_id(
        self, assessment_id: str, tenant_id: str | None = None
    ) -> Assessment | None:
        statement = select(AssessmentModel).where(AssessmentModel.id == assessment_id)
        if tenant_id is not None:
            statement = statement.where(AssessmentModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(AssessmentModel.questions))
        result = await self._session.scalars(statement)
        model = result.first()
        return assessment_model_to_domain(model) if model is not None else None

    async def list_by_course(
        self, course_id: str, tenant_id: str | None = None
    ) -> list[Assessment]:
        statement = select(AssessmentModel).where(
            AssessmentModel.course_id == course_id
        )
        if tenant_id is not None:
            statement = statement.where(AssessmentModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(AssessmentModel.questions))
        result = await self._session.scalars(statement)
        return [assessment_model_to_domain(item) for item in result.all()]

    async def list_all(self, tenant_id: str | None = None) -> list[Assessment]:
        statement = select(AssessmentModel)
        if tenant_id is not None:
            statement = statement.where(AssessmentModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(AssessmentModel.questions))
        result = await self._session.scalars(statement)
        return [assessment_model_to_domain(item) for item in result.all()]

    async def update(
        self, assessment: Assessment, tenant_id: str | None = None
    ) -> Assessment:
        statement = select(AssessmentModel).where(AssessmentModel.id == assessment.id)
        if tenant_id is not None:
            statement = statement.where(AssessmentModel.tenant_id == tenant_id)
        statement = statement.options(selectinload(AssessmentModel.questions))
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            raise ValueError(f"assessment {assessment.id} not found")
        assessment_to_model(assessment, model=model)
        await self._session.flush()
        return assessment

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.assessment.assessment import Assessment, AssessmentQuestion
from app.domain.assessment.attempt import AssessmentAttempt, AttemptStatus
from app.domain.assessment.attempt_answer import AttemptAnswer
from app.domain.assessment.question import Question
from app.domain.assessment.result import AttemptResult
from app.domain.repositories.assessment import AssessmentRepository
from app.domain.repositories.attempt import AttemptRepository
from app.domain.repositories.attempt_answer import AttemptAnswerRepository
from app.domain.repositories.attempt_result import AttemptResultRepository
from app.domain.repositories.question import QuestionRepository
from app.infrastructure.assessment.mappers import (
    assessment_model_to_domain,
    assessment_question_model_to_domain,
    assessment_to_model,
    attempt_answer_model_to_domain,
    attempt_answer_to_model,
    attempt_model_to_domain,
    attempt_result_model_to_domain,
    attempt_result_to_model,
    attempt_to_model,
    question_model_to_domain,
    question_to_model,
)
from app.infrastructure.db.models.assessment import (
    AssessmentAttemptModel,
    AssessmentAttemptResultModel,
    AssessmentModel,
    AssessmentQuestionModel,
    AttemptAnswerModel,
    QuestionModel,
)


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

    async def list_question_snapshots(
        self, assessment_id: str, tenant_id: str
    ) -> list[AssessmentQuestion]:
        statement = (
            select(AssessmentQuestionModel)
            .join(AssessmentModel)
            .where(
                AssessmentQuestionModel.assessment_id == assessment_id,
                AssessmentModel.tenant_id == tenant_id,
                AssessmentQuestionModel.is_active.is_(True),
            )
            .order_by(AssessmentQuestionModel.sequence.asc())
        )
        result = await self._session.scalars(statement)
        return [assessment_question_model_to_domain(item) for item in result.all()]

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


class SqlAlchemyAttemptRepository(AttemptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self, attempt: AssessmentAttempt, tenant_id: str | None = None
    ) -> AssessmentAttempt:
        model = await self._find(attempt.id, tenant_id=tenant_id)
        if model is None:
            model = attempt_to_model(attempt)
            if tenant_id is not None:
                model.tenant_id = tenant_id
            self._session.add(model)
        else:
            attempt_to_model(attempt, model=model)
        await self._session.flush()
        return attempt

    async def get_by_id(
        self,
        attempt_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> AssessmentAttempt | None:
        statement = select(AssessmentAttemptModel).where(
            AssessmentAttemptModel.id == attempt_id
        )
        if tenant_id is not None:
            statement = statement.where(AssessmentAttemptModel.tenant_id == tenant_id)
        if user_id is not None:
            statement = statement.where(AssessmentAttemptModel.user_id == user_id)
        result = await self._session.scalars(statement)
        model = result.first()
        return attempt_model_to_domain(model) if model is not None else None

    async def get_active_for_user(
        self,
        assessment_id: str,
        user_id: str,
        tenant_id: str,
    ) -> AssessmentAttempt | None:
        statement = select(AssessmentAttemptModel).where(
            AssessmentAttemptModel.assessment_id == assessment_id,
            AssessmentAttemptModel.user_id == user_id,
            AssessmentAttemptModel.tenant_id == tenant_id,
            AssessmentAttemptModel.status == AttemptStatus.IN_PROGRESS.value,
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return attempt_model_to_domain(model) if model is not None else None

    async def list_by_user(
        self, user_id: str, tenant_id: str
    ) -> list[AssessmentAttempt]:
        statement = select(AssessmentAttemptModel).where(
            AssessmentAttemptModel.user_id == user_id,
            AssessmentAttemptModel.tenant_id == tenant_id,
        )
        result = await self._session.scalars(statement)
        return [attempt_model_to_domain(item) for item in result.all()]

    async def update(
        self, attempt: AssessmentAttempt, tenant_id: str | None = None
    ) -> AssessmentAttempt:
        model = await self._find(attempt.id, tenant_id=tenant_id)
        if model is None:
            raise ValueError(f"attempt {attempt.id} not found")
        attempt_to_model(attempt, model=model)
        await self._session.flush()
        return attempt

    async def _find(
        self, attempt_id: str, tenant_id: str | None = None
    ) -> AssessmentAttemptModel | None:
        statement = select(AssessmentAttemptModel).where(
            AssessmentAttemptModel.id == attempt_id
        )
        if tenant_id is not None:
            statement = statement.where(AssessmentAttemptModel.tenant_id == tenant_id)
        result = await self._session.scalars(statement)
        return result.first()


class SqlAlchemyAttemptAnswerRepository(AttemptAnswerRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_attempt_and_question(
        self,
        attempt_id: str,
        assessment_question_id: str,
        tenant_id: str,
    ) -> AttemptAnswer | None:
        statement = select(AttemptAnswerModel).where(
            AttemptAnswerModel.attempt_id == attempt_id,
            AttemptAnswerModel.assessment_question_id == assessment_question_id,
            AttemptAnswerModel.tenant_id == tenant_id,
        )
        model = (await self._session.scalars(statement)).first()
        return attempt_answer_model_to_domain(model) if model is not None else None

    async def list_by_attempt(
        self, attempt_id: str, tenant_id: str
    ) -> list[AttemptAnswer]:
        statement = (
            select(AttemptAnswerModel)
            .where(
                AttemptAnswerModel.attempt_id == attempt_id,
                AttemptAnswerModel.tenant_id == tenant_id,
            )
            .order_by(AttemptAnswerModel.created_at.asc())
        )
        models = (await self._session.scalars(statement)).all()
        return [attempt_answer_model_to_domain(model) for model in models]

    async def save(self, answer: AttemptAnswer) -> AttemptAnswer:
        statement = select(AttemptAnswerModel).where(
            AttemptAnswerModel.id == answer.id,
            AttemptAnswerModel.tenant_id == answer.tenant_id,
        )
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = attempt_answer_to_model(answer)
            self._session.add(model)
        else:
            attempt_answer_to_model(answer, model=model)
        await self._session.flush()
        return answer

    async def delete(self, answer: AttemptAnswer) -> None:
        statement = select(AttemptAnswerModel).where(
            AttemptAnswerModel.id == answer.id,
            AttemptAnswerModel.tenant_id == answer.tenant_id,
        )
        model = (await self._session.scalars(statement)).first()
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()


class SqlAlchemyAttemptResultRepository(AttemptResultRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_attempt_id(
        self, attempt_id: str, tenant_id: str
    ) -> AttemptResult | None:
        statement = select(AssessmentAttemptResultModel).where(
            AssessmentAttemptResultModel.attempt_id == attempt_id,
            AssessmentAttemptResultModel.tenant_id == tenant_id,
        )
        model = (await self._session.scalars(statement)).first()
        return attempt_result_model_to_domain(model) if model is not None else None

    async def get_by_id(self, result_id: str, tenant_id: str) -> AttemptResult | None:
        statement = select(AssessmentAttemptResultModel).where(
            AssessmentAttemptResultModel.id == result_id,
            AssessmentAttemptResultModel.tenant_id == tenant_id,
        )
        model = (await self._session.scalars(statement)).first()
        return attempt_result_model_to_domain(model) if model is not None else None

    async def list_by_user(self, user_id: str, tenant_id: str) -> list[AttemptResult]:
        statement = (
            select(AssessmentAttemptResultModel)
            .where(
                AssessmentAttemptResultModel.user_id == user_id,
                AssessmentAttemptResultModel.tenant_id == tenant_id,
            )
            .order_by(AssessmentAttemptResultModel.graded_at.desc())
        )
        models = (await self._session.scalars(statement)).all()
        return [attempt_result_model_to_domain(model) for model in models]

    async def save(self, result: AttemptResult) -> AttemptResult:
        statement = select(AssessmentAttemptResultModel).where(
            AssessmentAttemptResultModel.id == result.id,
            AssessmentAttemptResultModel.tenant_id == result.tenant_id,
        )
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = attempt_result_to_model(result)
            self._session.add(model)
        else:
            attempt_result_to_model(result, model=model)
        await self._session.flush()
        return result

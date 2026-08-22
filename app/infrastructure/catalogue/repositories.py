from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.catalogue.course import Course
from app.domain.repositories.course import CourseRepository
from app.infrastructure.catalogue.mappers import course_to_domain, course_to_model
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    LearningOutcomeModel,
    TopicModel,
)


class SqlAlchemyCourseRepository(CourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, course: Course, tenant_id: str | None = None) -> Course:
        statement = select(CourseModel).where(CourseModel.id == course.id.value)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            model = course_to_model(course)
            if tenant_id is not None:
                model.tenant_id = tenant_id
            self._session.add(model)
        else:
            course_to_model(course, model=model)
            if tenant_id is not None:
                model.tenant_id = tenant_id
        await self._session.flush()
        return course

    async def get_by_id(self, course_id: str, tenant_id: str | None = None) -> Course | None:
        statement = select(CourseModel).where(CourseModel.id == course_id)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return course_to_domain(model) if model is not None else None

    async def list_by_department(self, department_id: str, tenant_id: str | None = None) -> list[Course]:
        statement = select(CourseModel).where(CourseModel.department_id == department_id)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        return [course_to_domain(c) for c in result.all()]

    async def list_all(self, tenant_id: str | None = None) -> list[Course]:
        statement = select(CourseModel)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        return [course_to_domain(c) for c in result.all()]

    async def get_by_topic_id(
        self, topic_id: str, tenant_id: str | None = None
    ) -> Course | None:
        statement = (
            select(CourseModel)
            .join(TopicModel, TopicModel.course_id == CourseModel.id)
            .where(TopicModel.id == topic_id)
        )
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return course_to_domain(model) if model is not None else None

    async def get_by_learning_outcome_id(
        self, learning_outcome_id: str, tenant_id: str | None = None
    ) -> Course | None:
        statement = (
            select(CourseModel)
            .join(TopicModel, TopicModel.course_id == CourseModel.id)
            .join(
                LearningOutcomeModel,
                LearningOutcomeModel.topic_id == TopicModel.id,
            )
            .where(LearningOutcomeModel.id == learning_outcome_id)
        )
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return course_to_domain(model) if model is not None else None

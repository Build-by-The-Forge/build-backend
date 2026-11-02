from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.catalogue.course import Course
from app.domain.catalogue.value_objects import CourseStatus
from app.domain.repositories.course import CourseRepository
from app.infrastructure.catalogue.mappers import course_to_domain, course_to_model
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    LearningOutcomeModel,
    ReferenceMaterialModel,
    TopicModel,
)
from app.infrastructure.db.models.tenant_core import DepartmentModel


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

    async def has_active_department(self, department_id: str, tenant_id: str) -> bool:
        found = await self._session.scalar(
            select(DepartmentModel.id).where(
                DepartmentModel.id == department_id,
                DepartmentModel.tenant_id == tenant_id,
                DepartmentModel.status == "active",
            )
        )
        return found is not None

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

    async def list_page(
        self,
        tenant_id: str,
        department_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Course], int]:
        conditions = [CourseModel.tenant_id == tenant_id]
        if department_id is not None:
            conditions.append(CourseModel.department_id == department_id)
        if active_only:
            conditions.append(CourseModel.status == CourseStatus.ACTIVE.value)
        total = await self._session.scalar(select(func.count()).select_from(CourseModel).where(*conditions))
        statement = (
            select(CourseModel)
            .where(*conditions)
            .order_by(CourseModel.code, CourseModel.id)
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
                selectinload(CourseModel.reference_materials),
            )
        )
        result = await self._session.scalars(statement)
        return [course_to_domain(c) for c in result.all()], total or 0

    async def get_by_topic_id(self, topic_id: str, tenant_id: str | None = None) -> Course | None:
        statement = select(CourseModel).join(TopicModel, TopicModel.course_id == CourseModel.id).where(TopicModel.id == topic_id)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        return course_to_domain(model) if model is not None else None

    async def get_by_learning_outcome_id(self, learning_outcome_id: str, tenant_id: str | None = None) -> Course | None:
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

    async def get_by_reference_material_id(self, reference_material_id: str, tenant_id: str | None = None) -> Course | None:
        statement = (
            select(CourseModel)
            .join(
                ReferenceMaterialModel,
                ReferenceMaterialModel.course_id == CourseModel.id,
            )
            .where(ReferenceMaterialModel.id == reference_material_id)
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

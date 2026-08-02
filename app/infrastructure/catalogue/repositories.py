from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.catalogue.course import Course
from app.domain.repositories.course import CourseRepository
from app.infrastructure.catalogue.mappers import course_to_domain, course_to_model
from app.infrastructure.db.models.catalogue import CourseModel


class SqlAlchemyCourseRepository(CourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, course: Course) -> Course:
        model = await self._session.get(CourseModel, course.id.value)
        if model is None:
            model = course_to_model(course)
            self._session.add(model)
        else:
            model = course_to_model(course, model=model)
        await self._session.flush()
        return course

    async def get_by_id(self, course_id: str) -> Course | None:
        model = await self._session.get(CourseModel, course_id)
        return course_to_domain(model) if model is not None else None

    async def list_by_department(self, department_id: str) -> list[Course]:
        statement = select(CourseModel).where(
            CourseModel.department_id == department_id
        )
        result = await self._session.scalars(statement)
        return [course_to_domain(c) for c in result.all()]

    async def list_all(self) -> list[Course]:
        statement = select(CourseModel)
        result = await self._session.scalars(statement)
        return [course_to_domain(c) for c in result.all()]

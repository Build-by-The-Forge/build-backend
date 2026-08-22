from collections.abc import AsyncIterator

from app.application.catalogue.commands import CreateCourseCommand
from app.application.catalogue.handlers import (
    CreateCourseHandler,
    ListCoursesHandler,
    TransitionCourseHandler,
    UpdateCourseHandler,
)
from app.application.catalogue.commands import UpdateCourseCommand
from app.domain.repositories.course import CourseRepository

AsyncUnitOfWorkFactory = AsyncIterator[object]


class CourseService:
    def __init__(
        self,
        repository: CourseRepository | None = None,
        uow_factory: AsyncUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.uow_factory = uow_factory

    async def create_course(
        self,
        department_id: str,
        code: str,
        title: str,
        slug: str,
        credit_units: int,
        level: int,
        semester: int,
        description: str | None = None,
        tenant_id: str | None = None,
    ):
        command = CreateCourseCommand(
            department_id=department_id,
            code=code,
            title=title,
            slug=slug,
            credit_units=credit_units,
            level=level,
            semester=semester,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = CreateCourseHandler(repository=uow.courses)
                return await handler.handle(command)

        handler = CreateCourseHandler(repository=self.repository)
        return await handler.handle(command)

    async def list_courses(
        self, department_id: str | None = None, tenant_id: str | None = None
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ListCoursesHandler(repository=uow.courses)
                return await handler.handle(
                    department_id=department_id, tenant_id=tenant_id
                )

        handler = ListCoursesHandler(repository=self.repository)
        return await handler.handle(
            department_id=department_id, tenant_id=tenant_id
        )

    async def get_course(self, course_id: str, tenant_id: str | None = None):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await uow.courses.get_by_id(course_id, tenant_id=tenant_id)

        return await self.repository.get_by_id(course_id, tenant_id=tenant_id)

    async def update_course(
        self,
        course_id: str,
        tenant_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ):
        command = UpdateCourseCommand(
            course_id=course_id,
            title=title,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await UpdateCourseHandler(uow.courses).handle(command)
        return await UpdateCourseHandler(self.repository).handle(command)

    async def transition_course(
        self, course_id: str, tenant_id: str | None, transition: str
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await TransitionCourseHandler(uow.courses).handle(
                    course_id, tenant_id, transition
                )
        return await TransitionCourseHandler(self.repository).handle(
            course_id, tenant_id, transition
        )

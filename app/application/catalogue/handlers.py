from app.application.catalogue.commands import CreateCourseCommand
from app.domain.catalogue.course import Course
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseTitle,
    DepartmentId,
)
from app.domain.repositories.course import CourseRepository


class CreateCourseHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateCourseCommand) -> Course:
        course = Course.create(
            department_id=DepartmentId(command.department_id),
            code=CourseCode(command.code),
            title=CourseTitle(command.title),
            slug=CourseSlug(command.slug),
            credit_units=CourseCreditUnits(command.credit_units),
            level=CourseLevel(command.level),
            semester=CourseSemester(command.semester),
            description=command.description,
        )
        return await self.repository.save(course, tenant_id=command.tenant_id)


class ListCoursesHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(
        self, department_id: str | None = None, tenant_id: str | None = None
    ) -> list[Course]:
        if department_id:
            return await self.repository.list_by_department(
                department_id, tenant_id=tenant_id
            )
        return await self.repository.list_all(tenant_id=tenant_id)

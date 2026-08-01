from typing import Protocol

from app.domain.catalogue.course import Course


class CourseRepository(Protocol):
    async def save(self, course: Course) -> Course:
        raise NotImplementedError

    async def get_by_id(self, course_id: str) -> Course | None:
        raise NotImplementedError

    async def list_by_department(self, department_id: str) -> list[Course]:
        raise NotImplementedError

    async def list_all(self) -> list[Course]:
        raise NotImplementedError

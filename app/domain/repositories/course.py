from typing import Protocol

from app.domain.catalogue.course import Course


class CourseRepository(Protocol):
    async def save(self, course: Course, tenant_id: str | None = None) -> Course:
        raise NotImplementedError

    async def get_by_id(self, course_id: str, tenant_id: str | None = None) -> Course | None:
        raise NotImplementedError

    async def list_by_department(self, department_id: str, tenant_id: str | None = None) -> list[Course]:
        raise NotImplementedError

    async def list_all(self, tenant_id: str | None = None) -> list[Course]:
        raise NotImplementedError

    async def get_by_topic_id(
        self, topic_id: str, tenant_id: str | None = None
    ) -> Course | None:
        raise NotImplementedError

    async def get_by_learning_outcome_id(
        self, learning_outcome_id: str, tenant_id: str | None = None
    ) -> Course | None:
        raise NotImplementedError

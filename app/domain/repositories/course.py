from typing import Protocol

from app.domain.catalogue.course import Course


class CourseRepository(Protocol):
    async def save(self, course: Course, tenant_id: str | None = None) -> Course:
        raise NotImplementedError

    async def has_active_department(self, department_id: str, tenant_id: str) -> bool:
        raise NotImplementedError

    async def get_by_id(self, course_id: str, tenant_id: str | None = None) -> Course | None:
        raise NotImplementedError

    async def list_page(
        self,
        tenant_id: str,
        department_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Course], int]:
        raise NotImplementedError

    async def get_by_topic_id(self, topic_id: str, tenant_id: str | None = None) -> Course | None:
        raise NotImplementedError

    async def get_by_learning_outcome_id(self, learning_outcome_id: str, tenant_id: str | None = None) -> Course | None:
        raise NotImplementedError

    async def get_by_reference_material_id(self, reference_material_id: str, tenant_id: str | None = None) -> Course | None:
        raise NotImplementedError

from typing import Protocol

from app.domain.assessment.assessment import Assessment, AssessmentQuestion


class AssessmentRepository(Protocol):
    async def save(self, assessment: Assessment, tenant_id: str | None = None) -> Assessment:
        raise NotImplementedError

    async def lock_for_change(self, assessment_id: str, tenant_id: str) -> None:
        """Hold the row until the transaction ends. Read the assessment after this."""
        raise NotImplementedError

    async def get_by_id(self, assessment_id: str, tenant_id: str | None = None) -> Assessment | None:
        raise NotImplementedError

    async def list_by_course(self, course_id: str, tenant_id: str | None = None) -> list[Assessment]:
        raise NotImplementedError

    async def list_all(self, tenant_id: str | None = None) -> list[Assessment]:
        raise NotImplementedError

    async def list_question_snapshots(self, assessment_id: str, tenant_id: str) -> list[AssessmentQuestion]:
        raise NotImplementedError

    async def update(self, assessment: Assessment, tenant_id: str | None = None) -> Assessment:
        raise NotImplementedError

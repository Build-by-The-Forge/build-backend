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

    async def list_readable(self, tenant_id: str, course_id: str | None = None) -> list[tuple[Assessment, int]]:
        """Published assessments whose course, department and faculty are all
        active: what the mobile routes show, to everyone (M3-E). Each comes
        with its question count and without its questions: the mobile routes
        never return them, so their answer-bearing rows aren't loaded."""
        raise NotImplementedError

    async def get_readable(self, assessment_id: str, tenant_id: str) -> tuple[Assessment, int] | None:
        """The assessment and its question count if list_readable would include it."""
        raise NotImplementedError

    async def list_question_snapshots(self, assessment_id: str, tenant_id: str) -> list[AssessmentQuestion]:
        raise NotImplementedError

    async def update(self, assessment: Assessment, tenant_id: str | None = None) -> Assessment:
        raise NotImplementedError

from typing import Protocol

from app.domain.assessment.attempt import AssessmentAttempt


class AttemptRepository(Protocol):
    async def save(
        self, attempt: AssessmentAttempt, tenant_id: str | None = None
    ) -> AssessmentAttempt:
        raise NotImplementedError

    async def get_by_id(
        self,
        attempt_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> AssessmentAttempt | None:
        raise NotImplementedError

    async def get_active_for_user(
        self,
        assessment_id: str,
        user_id: str,
        tenant_id: str,
    ) -> AssessmentAttempt | None:
        raise NotImplementedError

    async def list_by_user(
        self, user_id: str, tenant_id: str
    ) -> list[AssessmentAttempt]:
        raise NotImplementedError

    async def update(
        self, attempt: AssessmentAttempt, tenant_id: str | None = None
    ) -> AssessmentAttempt:
        raise NotImplementedError

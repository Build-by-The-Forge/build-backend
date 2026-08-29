from typing import Protocol

from app.domain.assessment.result import AttemptResult


class AttemptResultRepository(Protocol):
    async def save(self, result: AttemptResult) -> AttemptResult:
        raise NotImplementedError

    async def get_by_attempt_id(
        self, attempt_id: str, tenant_id: str
    ) -> AttemptResult | None:
        raise NotImplementedError

    async def get_by_id(self, result_id: str, tenant_id: str) -> AttemptResult | None:
        raise NotImplementedError

    async def list_by_user(self, user_id: str, tenant_id: str) -> list[AttemptResult]:
        raise NotImplementedError

    async def list_by_assessment(
        self,
        assessment_id: str,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AttemptResult], int]:
        raise NotImplementedError

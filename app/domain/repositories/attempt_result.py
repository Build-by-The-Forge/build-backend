from typing import Protocol

from app.domain.assessment.result import AttemptResult
from app.domain.assessment.result_disclosure import AttemptOutcome
from app.domain.assessment.result_release import ResultRelease


class ResultReleaseRepository(Protocol):
    async def get(self, assessment_id: str, tenant_id: str) -> ResultRelease | None:
        raise NotImplementedError

    async def insert_if_absent(self, release: ResultRelease) -> bool:
        """False if one exists. There is no update or delete: a release is final."""
        raise NotImplementedError


class AttemptResultRepository(Protocol):
    async def list_outcomes(self, assessment_id: str, tenant_id: str) -> list[AttemptOutcome]:
        raise NotImplementedError

    async def save(self, result: AttemptResult) -> AttemptResult:
        raise NotImplementedError

    async def get_by_attempt_id(self, attempt_id: str, tenant_id: str) -> AttemptResult | None:
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

from datetime import datetime
from typing import Protocol

from app.domain.assessment.attempt import AssessmentAttempt


class AttemptRepository(Protocol):
    async def save(self, attempt: AssessmentAttempt, tenant_id: str | None = None) -> AssessmentAttempt:
        raise NotImplementedError

    async def get_by_id_for_update(
        self,
        attempt_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> AssessmentAttempt | None:
        """As get_by_id, holding the row until the transaction ends."""
        ...

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

    async def database_now(self) -> datetime:
        """The one clock for deadlines. Read it after taking the row lock."""
        raise NotImplementedError

    async def claim_next_expired(self, excluded_ids: set[str]) -> AssessmentAttempt | None:
        raise NotImplementedError

    async def lock_starts(self, assessment_id: str, user_id: str, tenant_id: str) -> None:
        """One start at a time for this student and assessment, until the transaction ends."""
        raise NotImplementedError

    async def count_for_user(self, assessment_id: str, user_id: str, tenant_id: str) -> int:
        raise NotImplementedError

    async def counts_by_assessment(self, user_id: str, tenant_id: str) -> dict[str, int]:
        raise NotImplementedError

    async def insert_unless_active(self, attempt: AssessmentAttempt) -> bool:
        raise NotImplementedError

    async def list_by_user(self, user_id: str, tenant_id: str) -> list[AssessmentAttempt]:
        raise NotImplementedError

    async def update(self, attempt: AssessmentAttempt, tenant_id: str | None = None) -> AssessmentAttempt:
        raise NotImplementedError

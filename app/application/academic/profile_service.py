"""Reading and replacing the student's academic profile (S-02)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from app.domain.academic.profile import AcademicProfile
from app.domain.repositories.academic_profile import AcademicProfileRepository

# Opens one transaction, committed when the block succeeds and rolled back if it raises.
ProfileTransaction = Callable[[], AbstractAsyncContextManager[AcademicProfileRepository]]


class AcademicProfileService:
    def __init__(self, transaction: ProfileTransaction) -> None:
        self._transaction = transaction

    async def get(self, tenant_id: str, user_id: str) -> AcademicProfile:
        async with self._transaction() as profiles:
            return await profiles.read(tenant_id, user_id)

    async def replace(
        self, tenant_id: str, user_id: str, programme_id: str, level: int, course_ids: list[str]
    ) -> AcademicProfile:
        """Replace the whole profile and answer it as stored, in one transaction.
        Raises UnavailableReferences, having written nothing."""
        async with self._transaction() as profiles:
            await profiles.replace(tenant_id, user_id, programme_id, level, course_ids)
            return await profiles.read(tenant_id, user_id)

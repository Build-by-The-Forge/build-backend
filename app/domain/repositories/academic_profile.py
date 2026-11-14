from typing import Protocol

from app.domain.academic.profile import AcademicProfile


class AcademicProfileRepository(Protocol):
    async def read(self, tenant_id: str, user_id: str) -> AcademicProfile:
        """The profile as the student can read it; empty before the first save.
        Raises NotAStudentMember without an active student membership."""
        raise NotImplementedError

    async def replace(self, tenant_id: str, user_id: str, programme_id: str, level: int, course_ids: list[str]) -> None:
        """Replace the whole profile, or raise UnavailableReferences (or
        NotAStudentMember) and write nothing."""
        raise NotImplementedError

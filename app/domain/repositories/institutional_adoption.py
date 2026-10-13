from typing import Protocol

from app.domain.curriculum.adoption import (
    CurriculumOverride,
    InstitutionalAdoption,
)


class InstitutionalAdoptionRepository(Protocol):
    async def save_adoption(self, adoption: InstitutionalAdoption) -> InstitutionalAdoption:
        raise NotImplementedError

    async def get_adoption_by_id(self, adoption_id: str) -> InstitutionalAdoption | None:
        raise NotImplementedError

    async def get_active_adoption(
        self,
        tenant_id: str,
        programme_id: str,
        academic_session_id: str | None = None,
    ) -> InstitutionalAdoption | None:
        raise NotImplementedError

    async def list_adoptions_by_tenant(
        self,
        tenant_id: str,
        programme_id: str | None = None,
    ) -> list[InstitutionalAdoption]:
        raise NotImplementedError

    async def save_override(self, override: CurriculumOverride) -> CurriculumOverride:
        raise NotImplementedError

    async def list_overrides(self, adoption_id: str) -> list[CurriculumOverride]:
        raise NotImplementedError

    async def get_override(self, override_id: str) -> CurriculumOverride | None:
        raise NotImplementedError

    async def delete_override(self, override_id: str) -> bool:
        raise NotImplementedError

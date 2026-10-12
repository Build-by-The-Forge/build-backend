from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.curriculum.adoption import (
    AdoptionStatus,
    CurriculumOverride,
    InstitutionalAdoption,
    OverrideType,
)
from app.domain.repositories.institutional_adoption import (
    InstitutionalAdoptionRepository,
)
from app.infrastructure.db.models.institutional_curriculum import (
    CurriculumOverrideModel,
    InstitutionalAdoptionModel,
)


def _adoption_to_domain(model: InstitutionalAdoptionModel) -> InstitutionalAdoption:
    return InstitutionalAdoption(
        id=model.id,
        tenant_id=model.tenant_id,
        programme_id=model.programme_id,
        benchmark_curriculum_id=model.benchmark_curriculum_id,
        benchmark_version=model.benchmark_version,
        benchmark_fingerprint=model.benchmark_fingerprint,
        academic_session_id=model.academic_session_id,
        status=AdoptionStatus(model.status),
        notes=model.notes,
        adopted_by=model.adopted_by,
        adopted_by_email=model.adopted_by_email,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _override_to_domain(model: CurriculumOverrideModel) -> CurriculumOverride:
    return CurriculumOverride(
        id=model.id,
        adoption_id=model.adoption_id,
        override_type=OverrideType(model.override_type),
        target_course_code=model.target_course_code,
        target_topic_id=model.target_topic_id,
        target_outcome_id=model.target_outcome_id,
        field_overrides=model.field_overrides or {},
        custom_payload=model.custom_payload or {},
        reason=model.reason,
        created_by=model.created_by,
        created_by_email=model.created_by_email,
        created_at=model.created_at,
    )


class SqlAlchemyInstitutionalAdoptionRepository(InstitutionalAdoptionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_adoption(self, adoption: InstitutionalAdoption) -> InstitutionalAdoption:
        model = await self._session.get(InstitutionalAdoptionModel, adoption.id)
        if model is None:
            model = InstitutionalAdoptionModel(
                id=adoption.id,
                tenant_id=adoption.tenant_id,
                programme_id=adoption.programme_id,
                benchmark_curriculum_id=adoption.benchmark_curriculum_id,
                benchmark_version=adoption.benchmark_version,
                benchmark_fingerprint=adoption.benchmark_fingerprint,
                academic_session_id=adoption.academic_session_id,
                status=adoption.status.value,
                notes=adoption.notes,
                adopted_by=adoption.adopted_by,
                adopted_by_email=adoption.adopted_by_email,
                created_at=adoption.created_at,
                updated_at=adoption.updated_at,
            )
            self._session.add(model)
        else:
            model.status = adoption.status.value
            model.notes = adoption.notes
            model.updated_at = adoption.updated_at

        await self._session.flush()
        return adoption

    async def get_adoption_by_id(self, adoption_id: str) -> InstitutionalAdoption | None:
        model = await self._session.get(InstitutionalAdoptionModel, adoption_id)
        return _adoption_to_domain(model) if model is not None else None

    async def get_active_adoption(
        self,
        tenant_id: str,
        programme_id: str,
        academic_session_id: str | None = None,
    ) -> InstitutionalAdoption | None:
        statement = select(InstitutionalAdoptionModel).where(
            InstitutionalAdoptionModel.tenant_id == tenant_id,
            InstitutionalAdoptionModel.programme_id == programme_id,
            InstitutionalAdoptionModel.status == AdoptionStatus.ACTIVE.value,
        )
        if academic_session_id is not None:
            statement = statement.where(InstitutionalAdoptionModel.academic_session_id == academic_session_id)
        model = (await self._session.scalars(statement)).first()
        return _adoption_to_domain(model) if model is not None else None

    async def list_adoptions_by_tenant(
        self,
        tenant_id: str,
        programme_id: str | None = None,
    ) -> list[InstitutionalAdoption]:
        statement = (
            select(InstitutionalAdoptionModel)
            .where(InstitutionalAdoptionModel.tenant_id == tenant_id)
            .order_by(InstitutionalAdoptionModel.created_at.desc())
        )
        if programme_id is not None:
            statement = statement.where(InstitutionalAdoptionModel.programme_id == programme_id)
        models = (await self._session.scalars(statement)).all()
        return [_adoption_to_domain(m) for m in models]

    async def save_override(self, override: CurriculumOverride) -> CurriculumOverride:
        model = await self._session.get(CurriculumOverrideModel, override.id)
        if model is None:
            model = CurriculumOverrideModel(
                id=override.id,
                adoption_id=override.adoption_id,
                override_type=override.override_type.value,
                target_course_code=override.target_course_code,
                target_topic_id=override.target_topic_id,
                target_outcome_id=override.target_outcome_id,
                field_overrides=override.field_overrides,
                custom_payload=override.custom_payload,
                reason=override.reason,
                created_by=override.created_by,
                created_by_email=override.created_by_email,
                created_at=override.created_at,
            )
            self._session.add(model)
        else:
            model.field_overrides = override.field_overrides
            model.custom_payload = override.custom_payload
            model.reason = override.reason

        await self._session.flush()
        return override

    async def list_overrides(self, adoption_id: str) -> list[CurriculumOverride]:
        statement = (
            select(CurriculumOverrideModel)
            .where(CurriculumOverrideModel.adoption_id == adoption_id)
            .order_by(CurriculumOverrideModel.created_at.asc())
        )
        models = (await self._session.scalars(statement)).all()
        return [_override_to_domain(m) for m in models]

    async def get_override(self, override_id: str) -> CurriculumOverride | None:
        model = await self._session.get(CurriculumOverrideModel, override_id)
        return _override_to_domain(model) if model is not None else None

    async def delete_override(self, override_id: str) -> bool:
        model = await self._session.get(CurriculumOverrideModel, override_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

from __future__ import annotations

from app.application.curriculum.adoption_commands import (
    ActivateAdoptionCommand,
    AddCurriculumOverrideCommand,
    AdoptBenchmarkCurriculumCommand,
    GetAdoptionDetailCommand,
    ListAdoptionsCommand,
    RemoveCurriculumOverrideCommand,
)
from app.domain.curriculum.adoption import (
    CurriculumOverride,
    InstitutionalAdoption,
    OverrideType,
)
from app.domain.curriculum.benchmark import BenchmarkStatus
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.domain.repositories.institutional_adoption import (
    InstitutionalAdoptionRepository,
)
from app.events.base import DomainEvent


class AdoptBenchmarkCurriculumHandler:
    def __init__(
        self,
        adoption_repo: InstitutionalAdoptionRepository,
        benchmark_repo: BenchmarkCurriculumRepository,
    ) -> None:
        self.adoption_repo = adoption_repo
        self.benchmark_repo = benchmark_repo

    async def handle(self, command: AdoptBenchmarkCurriculumCommand) -> tuple[InstitutionalAdoption, list[DomainEvent]]:
        benchmark = await self.benchmark_repo.get_by_id(command.benchmark_curriculum_id)
        if benchmark is None:
            raise ValueError("benchmark curriculum not found")

        if benchmark.status not in (
            BenchmarkStatus.ACTIVE,
            BenchmarkStatus.APPROVED,
        ):
            raise ValueError(f"cannot adopt benchmark in status '{benchmark.status.value}', must be active or approved")

        adoption = InstitutionalAdoption.create_draft(
            tenant_id=command.tenant_id,
            programme_id=command.programme_id,
            benchmark_curriculum_id=benchmark.id,
            benchmark_version=benchmark.version,
            benchmark_fingerprint=benchmark.review_fingerprint,
            academic_session_id=command.academic_session_id,
            notes=command.notes,
            adopted_by=command.actor_id,
            adopted_by_email=command.actor_email,
        )
        await self.adoption_repo.save_adoption(adoption)
        return adoption, adoption.pull_events()


class AddCurriculumOverrideHandler:
    def __init__(
        self,
        adoption_repo: InstitutionalAdoptionRepository,
        benchmark_repo: BenchmarkCurriculumRepository,
    ) -> None:
        self.adoption_repo = adoption_repo
        self.benchmark_repo = benchmark_repo

    async def handle(self, command: AddCurriculumOverrideCommand) -> CurriculumOverride:
        adoption = await self.adoption_repo.get_adoption_by_id(command.adoption_id)
        if adoption is None or adoption.tenant_id != command.tenant_id:
            raise ValueError("adoption not found")

        if not adoption.is_editable():
            raise ValueError(
                f"cannot add overrides to adoption in status '{adoption.status.value}', overrides are immutable once activated"
            )

        ov_type = OverrideType(command.override_type) if isinstance(command.override_type, str) else command.override_type

        # Validate that course-level overrides target a course that exists in the adopted benchmark
        if ov_type in (
            OverrideType.MODIFY_COURSE,
            OverrideType.OMIT_COURSE,
        ):
            if not command.target_course_code:
                raise ValueError(f"target_course_code is required for override type '{ov_type.value}'")
            benchmark_courses = await self.benchmark_repo.list_courses(adoption.benchmark_curriculum_id)
            existing_codes = {c.code.upper() for c in benchmark_courses}
            if command.target_course_code.upper() not in existing_codes:
                raise ValueError(
                    f"target course '{command.target_course_code}' "
                    f"does not exist in adopted benchmark {adoption.benchmark_version}"
                )

        override = CurriculumOverride.create(
            adoption_id=adoption.id,
            override_type=ov_type,
            reason=command.reason,
            created_by=command.actor_id,
            created_by_email=command.actor_email,
            target_course_code=command.target_course_code,
            target_topic_id=command.target_topic_id,
            target_outcome_id=command.target_outcome_id,
            field_overrides=command.field_overrides,
            custom_payload=command.custom_payload,
        )
        await self.adoption_repo.save_override(override)
        return override


class RemoveCurriculumOverrideHandler:
    def __init__(self, adoption_repo: InstitutionalAdoptionRepository) -> None:
        self.adoption_repo = adoption_repo

    async def handle(self, command: RemoveCurriculumOverrideCommand) -> bool:
        adoption = await self.adoption_repo.get_adoption_by_id(command.adoption_id)
        if adoption is None or adoption.tenant_id != command.tenant_id:
            raise ValueError("adoption not found")

        if not adoption.is_editable():
            raise ValueError(
                f"cannot remove overrides from adoption in status '{adoption.status.value}', historical adoptions are immutable"
            )

        override = await self.adoption_repo.get_override(command.override_id)
        if override is None or override.adoption_id != adoption.id:
            raise ValueError("override not found in adoption")

        return await self.adoption_repo.delete_override(command.override_id)


class ActivateAdoptionHandler:
    def __init__(self, adoption_repo: InstitutionalAdoptionRepository) -> None:
        self.adoption_repo = adoption_repo

    async def handle(
        self, command: ActivateAdoptionCommand
    ) -> tuple[InstitutionalAdoption, InstitutionalAdoption | None, list[DomainEvent]]:
        adoption = await self.adoption_repo.get_adoption_by_id(command.adoption_id)
        if adoption is None or adoption.tenant_id != command.tenant_id:
            raise ValueError("adoption not found")

        all_events: list[DomainEvent] = []

        # Find existing active adoption for same tenant, programme, and session
        existing_active = await self.adoption_repo.get_active_adoption(
            tenant_id=adoption.tenant_id,
            programme_id=adoption.programme_id,
            academic_session_id=adoption.academic_session_id,
        )
        if existing_active is not None and existing_active.id != adoption.id:
            existing_active.supersede()
            await self.adoption_repo.save_adoption(existing_active)
            all_events.extend(existing_active.pull_events())

        adoption.activate(activated_by=command.actor_id)
        await self.adoption_repo.save_adoption(adoption)
        all_events.extend(adoption.pull_events())

        return adoption, existing_active, all_events


class GetAdoptionDetailHandler:
    def __init__(self, adoption_repo: InstitutionalAdoptionRepository) -> None:
        self.adoption_repo = adoption_repo

    async def handle(self, command: GetAdoptionDetailCommand) -> tuple[InstitutionalAdoption, list[CurriculumOverride]]:
        adoption = await self.adoption_repo.get_adoption_by_id(command.adoption_id)
        if adoption is None or adoption.tenant_id != command.tenant_id:
            raise ValueError("adoption not found")

        overrides = await self.adoption_repo.list_overrides(adoption.id)
        return adoption, overrides


class ListAdoptionsHandler:
    def __init__(self, adoption_repo: InstitutionalAdoptionRepository) -> None:
        self.adoption_repo = adoption_repo

    async def handle(self, command: ListAdoptionsCommand) -> list[InstitutionalAdoption]:
        return await self.adoption_repo.list_adoptions_by_tenant(
            tenant_id=command.tenant_id,
            programme_id=command.programme_id,
        )

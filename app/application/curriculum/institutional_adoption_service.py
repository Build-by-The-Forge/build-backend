from __future__ import annotations

from typing import Any

from app.application.common.uow import CurriculumUnitOfWorkFactory
from app.application.curriculum.adoption_commands import (
    ActivateAdoptionCommand,
    AddCurriculumOverrideCommand,
    AdoptBenchmarkCurriculumCommand,
    GetAdoptionDetailCommand,
    ListAdoptionsCommand,
    RemoveCurriculumOverrideCommand,
)
from app.application.curriculum.adoption_handlers import (
    ActivateAdoptionHandler,
    AddCurriculumOverrideHandler,
    AdoptBenchmarkCurriculumHandler,
    GetAdoptionDetailHandler,
    ListAdoptionsHandler,
    RemoveCurriculumOverrideHandler,
)
from app.application.curriculum.effective_handlers import (
    GetActiveEffectiveCurriculumHandler,
    GetEffectiveCurriculumByAdoptionHandler,
)
from app.application.curriculum.effective_queries import (
    GetActiveEffectiveCurriculumQuery,
    GetEffectiveCurriculumByAdoptionQuery,
)
from app.domain.curriculum.adoption import (
    CurriculumOverride,
    InstitutionalAdoption,
    OverrideType,
)
from app.domain.curriculum.effective import EffectiveCurriculum
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.domain.repositories.institutional_adoption import (
    InstitutionalAdoptionRepository,
)
from app.events.base import DomainEvent
from app.events.event_bus import EventBus


class InstitutionalAdoptionService:
    def __init__(
        self,
        adoption_repository: InstitutionalAdoptionRepository | None = None,
        benchmark_repository: BenchmarkCurriculumRepository | None = None,
        event_bus: EventBus | None = None,
        uow_factory: CurriculumUnitOfWorkFactory | None = None,
    ) -> None:
        self.adoption_repository = adoption_repository
        self.benchmark_repository = benchmark_repository
        self.event_bus = event_bus
        self.uow_factory = uow_factory

    async def adopt_benchmark(
        self,
        tenant_id: str,
        programme_id: str,
        benchmark_curriculum_id: str,
        actor_id: str,
        actor_email: str,
        academic_session_id: str | None = None,
        notes: str | None = None,
    ) -> InstitutionalAdoption:
        command = AdoptBenchmarkCurriculumCommand(
            tenant_id=tenant_id,
            programme_id=programme_id,
            benchmark_curriculum_id=benchmark_curriculum_id,
            actor_id=actor_id,
            actor_email=actor_email,
            academic_session_id=academic_session_id,
            notes=notes,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                adoption, events = await AdoptBenchmarkCurriculumHandler(uow.adoptions, uow.benchmarks).handle(command)
            self._publish_events(events)
            return adoption

        adoption, events = await AdoptBenchmarkCurriculumHandler(
            self._required_adoption_repo(),
            self._required_benchmark_repo(),
        ).handle(command)
        self._publish_events(events)
        return adoption

    async def add_override(
        self,
        adoption_id: str,
        tenant_id: str,
        override_type: OverrideType | str,
        reason: str,
        actor_id: str,
        actor_email: str,
        target_course_code: str | None = None,
        target_topic_id: str | None = None,
        target_outcome_id: str | None = None,
        field_overrides: dict[str, Any] | None = None,
        custom_payload: dict[str, Any] | None = None,
    ) -> CurriculumOverride:
        command = AddCurriculumOverrideCommand(
            adoption_id=adoption_id,
            tenant_id=tenant_id,
            override_type=override_type,
            reason=reason,
            actor_id=actor_id,
            actor_email=actor_email,
            target_course_code=target_course_code,
            target_topic_id=target_topic_id,
            target_outcome_id=target_outcome_id,
            field_overrides=field_overrides,
            custom_payload=custom_payload,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await AddCurriculumOverrideHandler(uow.adoptions, uow.benchmarks).handle(command)

        return await AddCurriculumOverrideHandler(
            self._required_adoption_repo(),
            self._required_benchmark_repo(),
        ).handle(command)

    async def remove_override(
        self,
        adoption_id: str,
        override_id: str,
        tenant_id: str,
    ) -> bool:
        command = RemoveCurriculumOverrideCommand(
            adoption_id=adoption_id,
            override_id=override_id,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await RemoveCurriculumOverrideHandler(uow.adoptions).handle(command)

        return await RemoveCurriculumOverrideHandler(self._required_adoption_repo()).handle(command)

    async def activate_adoption(
        self,
        adoption_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> tuple[InstitutionalAdoption, InstitutionalAdoption | None]:
        command = ActivateAdoptionCommand(
            adoption_id=adoption_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                adoption, superseded, events = await ActivateAdoptionHandler(uow.adoptions).handle(command)
            self._publish_events(events)
            return adoption, superseded

        adoption, superseded, events = await ActivateAdoptionHandler(self._required_adoption_repo()).handle(command)
        self._publish_events(events)
        return adoption, superseded

    async def get_adoption_detail(
        self,
        adoption_id: str,
        tenant_id: str,
    ) -> tuple[InstitutionalAdoption, list[CurriculumOverride]]:
        command = GetAdoptionDetailCommand(
            adoption_id=adoption_id,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetAdoptionDetailHandler(uow.adoptions).handle(command)

        return await GetAdoptionDetailHandler(self._required_adoption_repo()).handle(command)

    async def list_adoptions(
        self,
        tenant_id: str,
        programme_id: str | None = None,
    ) -> list[InstitutionalAdoption]:
        command = ListAdoptionsCommand(
            tenant_id=tenant_id,
            programme_id=programme_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await ListAdoptionsHandler(uow.adoptions).handle(command)

        return await ListAdoptionsHandler(self._required_adoption_repo()).handle(command)

    async def get_effective_curriculum(
        self,
        adoption_id: str,
        tenant_id: str,
    ) -> EffectiveCurriculum:
        query = GetEffectiveCurriculumByAdoptionQuery(
            adoption_id=adoption_id,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetEffectiveCurriculumByAdoptionHandler(uow.adoptions, uow.benchmarks).handle(query)

        return await GetEffectiveCurriculumByAdoptionHandler(
            self._required_adoption_repo(),
            self._required_benchmark_repo(),
        ).handle(query)

    async def get_active_effective_curriculum(
        self,
        tenant_id: str,
        programme_id: str,
        academic_session_id: str | None = None,
    ) -> EffectiveCurriculum:
        query = GetActiveEffectiveCurriculumQuery(
            tenant_id=tenant_id,
            programme_id=programme_id,
            academic_session_id=academic_session_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await GetActiveEffectiveCurriculumHandler(uow.adoptions, uow.benchmarks).handle(query)

        return await GetActiveEffectiveCurriculumHandler(
            self._required_adoption_repo(),
            self._required_benchmark_repo(),
        ).handle(query)

    def _required_adoption_repo(self) -> InstitutionalAdoptionRepository:
        if self.adoption_repository is None:
            raise ValueError("adoption repository is required")
        return self.adoption_repository

    def _required_benchmark_repo(self) -> BenchmarkCurriculumRepository:
        if self.benchmark_repository is None:
            raise ValueError("benchmark repository is required")
        return self.benchmark_repository

    def _publish_events(self, events: list[DomainEvent]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish_all(events)

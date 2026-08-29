from __future__ import annotations

from app.application.curriculum.activation_commands import (
    ActivateBenchmarkCurriculumCommand,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCurriculum,
    BenchmarkStatus,
)
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent


class ActivateBenchmarkCurriculumHandler:
    def __init__(self, repository: BenchmarkCurriculumRepository) -> None:
        self.repository = repository

    async def handle(
        self, command: ActivateBenchmarkCurriculumCommand
    ) -> tuple[BenchmarkCurriculum, BenchmarkCurriculum | None, list[DomainEvent]]:
        curriculum = await self.repository.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        if curriculum.status != BenchmarkStatus.VALIDATED:
            raise ValueError(
                f"only validated benchmarks can be activated, current status is '{curriculum.status.value}'"
            )

        all_events: list[DomainEvent] = []

        # Find currently active benchmark for this exact identity
        existing_active = await self.repository.get_active_by_programme(
            discipline_group=curriculum.discipline_group,
            programme_code=curriculum.programme_code,
            degree_level=curriculum.degree_level,
        )

        superseded_id: str | None = None
        if existing_active is not None and existing_active.id != curriculum.id:
            existing_active.supersede()
            await self.repository.save(existing_active)
            all_events.extend(existing_active.pull_events())
            superseded_id = existing_active.id

        curriculum.activate(
            superseded_id=superseded_id,
            activated_by=command.activated_by,
        )
        await self.repository.save(curriculum)
        all_events.extend(curriculum.pull_events())

        return curriculum, existing_active, all_events

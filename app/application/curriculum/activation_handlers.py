from app.application.curriculum.activation_commands import (
    ActivateBenchmarkCurriculumCommand,
)
from app.domain.curriculum.audit import (
    BenchmarkAuditAction,
    BenchmarkAuditLog,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCurriculum,
    BenchmarkStatus,
)
from app.domain.repositories.benchmark_audit import BenchmarkAuditRepository
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent


class ActivateBenchmarkCurriculumHandler:
    def __init__(
        self,
        repository: BenchmarkCurriculumRepository,
        audit_repo: BenchmarkAuditRepository | None = None,
    ) -> None:
        self.repository = repository
        self.audit_repo = audit_repo

    async def handle(
        self, command: ActivateBenchmarkCurriculumCommand
    ) -> tuple[BenchmarkCurriculum, BenchmarkCurriculum | None, list[DomainEvent]]:
        curriculum = await self.repository.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        if curriculum.status != BenchmarkStatus.APPROVED:
            raise ValueError(
                f"only approved benchmarks can be activated, current status is '{curriculum.status.value}'"
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
            existing_prev_status = existing_active.status.value
            existing_active.supersede()
            await self.repository.save(existing_active)
            all_events.extend(existing_active.pull_events())
            superseded_id = existing_active.id

            if self.audit_repo is not None:
                supersede_log = BenchmarkAuditLog.create(
                    curriculum_id=existing_active.id,
                    action=BenchmarkAuditAction.SUPERSEDE,
                    actor_id=command.activated_by or "system",
                    actor_email="system@build.internal",
                    previous_status=existing_prev_status,
                    new_status=existing_active.status.value,
                    reason=f"Superseded by new active version {curriculum.version} ({curriculum.id})",
                )
                await self.audit_repo.save(supersede_log)

        target_prev_status = curriculum.status.value
        curriculum.activate(
            superseded_id=superseded_id,
            activated_by=command.activated_by,
        )
        await self.repository.save(curriculum)
        all_events.extend(curriculum.pull_events())

        if self.audit_repo is not None:
            activate_log = BenchmarkAuditLog.create(
                curriculum_id=curriculum.id,
                action=BenchmarkAuditAction.ACTIVATE,
                actor_id=command.activated_by or "system",
                actor_email="system@build.internal",
                previous_status=target_prev_status,
                new_status=curriculum.status.value,
                diff_fingerprint=curriculum.review_fingerprint,
                metadata_payload={"superseded_id": superseded_id},
            )
            await self.audit_repo.save(activate_log)

        return curriculum, existing_active, all_events

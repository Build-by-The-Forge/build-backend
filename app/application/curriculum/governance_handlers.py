from __future__ import annotations

from app.application.curriculum.governance_commands import (
    ApproveBenchmarkCommand,
    GetBenchmarkAuditTrailCommand,
    RejectBenchmarkCommand,
    ReviseBenchmarkCommand,
    SubmitBenchmarkReviewCommand,
)
from app.domain.curriculum.audit import (
    BenchmarkAuditAction,
    BenchmarkAuditLog,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkStatus,
)
from app.domain.curriculum.diff import BenchmarkCurriculumDiffEngine
from app.domain.repositories.benchmark_audit import BenchmarkAuditRepository
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.events.base import DomainEvent


class SubmitBenchmarkReviewHandler:
    def __init__(
        self,
        benchmark_repo: BenchmarkCurriculumRepository,
        audit_repo: BenchmarkAuditRepository,
    ) -> None:
        self.benchmark_repo = benchmark_repo
        self.audit_repo = audit_repo
        self.diff_engine = BenchmarkCurriculumDiffEngine()

    async def handle(
        self, command: SubmitBenchmarkReviewCommand
    ) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog, list[DomainEvent]]:
        curriculum = await self.benchmark_repo.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        if curriculum.status != BenchmarkStatus.VALIDATED:
            raise ValueError(
                f"only validated benchmarks can be submitted for review, current status is '{curriculum.status.value}'"
            )

        previous_status = curriculum.status.value

        # Calculate diff from currently ACTIVE baseline version if one exists
        active_baseline = await self.benchmark_repo.get_active_by_programme(
            discipline_group=curriculum.discipline_group,
            programme_code=curriculum.programme_code,
            degree_level=curriculum.degree_level,
        )

        diff_fingerprint: str | None = None
        if active_baseline is not None and active_baseline.id != curriculum.id:
            active_courses = await self._load_full_courses(active_baseline.id)
            candidate_courses = await self._load_full_courses(curriculum.id)
            diff = self.diff_engine.compare(
                source_curriculum=active_baseline,
                source_courses=active_courses,
                target_curriculum=curriculum,
                target_courses=candidate_courses,
            )
            diff_fingerprint = diff.diff_fingerprint

        curriculum.submit_for_review(
            diff_fingerprint=diff_fingerprint,
            notes=command.notes,
        )
        await self.benchmark_repo.save(curriculum)

        audit_log = BenchmarkAuditLog.create(
            curriculum_id=curriculum.id,
            action=BenchmarkAuditAction.SUBMIT_REVIEW,
            actor_id=command.actor_id,
            actor_email=command.actor_email,
            previous_status=previous_status,
            new_status=curriculum.status.value,
            review_notes=command.notes,
            diff_fingerprint=diff_fingerprint,
        )
        await self.audit_repo.save(audit_log)

        return curriculum, audit_log, curriculum.pull_events()

    async def _load_full_courses(self, curriculum_id: str) -> list[BenchmarkCourse]:
        summaries = await self.benchmark_repo.list_courses(curriculum_id)
        full_courses: list[BenchmarkCourse] = []
        for s in summaries:
            course = await self.benchmark_repo.get_course(s.id)
            if course is not None:
                full_courses.append(course)
        return full_courses


class ApproveBenchmarkHandler:
    def __init__(
        self,
        benchmark_repo: BenchmarkCurriculumRepository,
        audit_repo: BenchmarkAuditRepository,
    ) -> None:
        self.benchmark_repo = benchmark_repo
        self.audit_repo = audit_repo

    async def handle(self, command: ApproveBenchmarkCommand) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog, list[DomainEvent]]:
        curriculum = await self.benchmark_repo.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        previous_status = curriculum.status.value

        curriculum.approve(
            reviewer_id=command.reviewer_id,
            reason=command.reason,
        )
        await self.benchmark_repo.save(curriculum)

        audit_log = BenchmarkAuditLog.create(
            curriculum_id=curriculum.id,
            action=BenchmarkAuditAction.APPROVE,
            actor_id=command.reviewer_id,
            actor_email=command.reviewer_email,
            previous_status=previous_status,
            new_status=curriculum.status.value,
            reason=command.reason,
            diff_fingerprint=curriculum.review_fingerprint,
        )
        await self.audit_repo.save(audit_log)

        return curriculum, audit_log, curriculum.pull_events()


class RejectBenchmarkHandler:
    def __init__(
        self,
        benchmark_repo: BenchmarkCurriculumRepository,
        audit_repo: BenchmarkAuditRepository,
    ) -> None:
        self.benchmark_repo = benchmark_repo
        self.audit_repo = audit_repo

    async def handle(self, command: RejectBenchmarkCommand) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog, list[DomainEvent]]:
        curriculum = await self.benchmark_repo.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        previous_status = curriculum.status.value

        curriculum.reject(
            reviewer_id=command.reviewer_id,
            reason=command.reason,
        )
        await self.benchmark_repo.save(curriculum)

        audit_log = BenchmarkAuditLog.create(
            curriculum_id=curriculum.id,
            action=BenchmarkAuditAction.REJECT,
            actor_id=command.reviewer_id,
            actor_email=command.reviewer_email,
            previous_status=previous_status,
            new_status=curriculum.status.value,
            reason=command.reason,
        )
        await self.audit_repo.save(audit_log)

        return curriculum, audit_log, curriculum.pull_events()


class ReviseBenchmarkHandler:
    def __init__(
        self,
        benchmark_repo: BenchmarkCurriculumRepository,
        audit_repo: BenchmarkAuditRepository,
    ) -> None:
        self.benchmark_repo = benchmark_repo
        self.audit_repo = audit_repo

    async def handle(self, command: ReviseBenchmarkCommand) -> tuple[BenchmarkCurriculum, BenchmarkAuditLog, list[DomainEvent]]:
        curriculum = await self.benchmark_repo.get_by_id(command.curriculum_id)
        if curriculum is None:
            raise ValueError("benchmark curriculum not found")

        previous_status = curriculum.status.value

        curriculum.revise_to_candidate()
        await self.benchmark_repo.save(curriculum)

        audit_log = BenchmarkAuditLog.create(
            curriculum_id=curriculum.id,
            action=BenchmarkAuditAction.REVISE,
            actor_id=command.actor_id,
            actor_email=command.actor_email,
            previous_status=previous_status,
            new_status=curriculum.status.value,
            reason=command.reason,
        )
        await self.audit_repo.save(audit_log)

        return curriculum, audit_log, curriculum.pull_events()


class GetBenchmarkAuditTrailHandler:
    def __init__(self, audit_repo: BenchmarkAuditRepository) -> None:
        self.audit_repo = audit_repo

    async def handle(self, command: GetBenchmarkAuditTrailCommand) -> list[BenchmarkAuditLog]:
        return await self.audit_repo.list_by_curriculum(command.curriculum_id)

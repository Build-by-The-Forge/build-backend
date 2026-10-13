import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.curriculum.benchmark_commands import (
    BenchmarkCourseInput,
    BenchmarkOutcomeInput,
    BenchmarkTopicInput,
)
from app.application.curriculum.benchmark_service import (
    BenchmarkCurriculumService,
)
from app.domain.curriculum.audit import BenchmarkAuditAction
from app.domain.curriculum.benchmark import BenchmarkStatus
from app.domain.curriculum.source import CurriculumSource
from app.events.event_bus import EventBus
from app.infrastructure.curriculum.audit_repositories import (
    SqlAlchemyBenchmarkAuditRepository,
)
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)


@pytest.mark.asyncio
async def test_benchmark_governance_workflow_and_audit_trail(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    audit_repo = SqlAlchemyBenchmarkAuditRepository(session)
    event_bus = EventBus()

    source = CurriculumSource.create(
        code="NUC_GOV_TEST",
        name="Governance Test Source",
        base_url="https://gov.example.com",
    )
    await source_repo.save_source(source)

    snap1 = source.create_snapshot(
        source_url="https://gov.example.com/v1.pdf",
        content_sha256="1" * 64,
        raw_artifact_uri="s3://build/v1.pdf",
    )
    await source_repo.save_snapshot(snap1)

    snap2 = source.create_snapshot(
        source_url="https://gov.example.com/v2.pdf",
        content_sha256="2" * 64,
        raw_artifact_uri="s3://build/v2.pdf",
    )
    await source_repo.save_snapshot(snap2)

    service = BenchmarkCurriculumService(
        repository=benchmark_repo,
        audit_repository=audit_repo,
        event_bus=event_bus,
    )

    course_input = BenchmarkCourseInput(
        code="CSC101",
        title="Intro to CS",
        credit_units=3,
        level=100,
        semester=1,
        sequence=1,
        topics=[
            BenchmarkTopicInput(
                sequence=1,
                title="Hardware",
                outcomes=[
                    BenchmarkOutcomeInput(
                        sequence=1,
                        description="Understand CPU.",
                        bloom_level="understand",
                    )
                ],
            )
        ],
    )

    # 1. Ingest V1
    v1, _ = await service.ingest_candidate(
        source_snapshot_id=snap1.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC_GOV",
        version="2026.01",
        courses=[course_input],
    )
    await service.validate_candidate(v1.id)

    # Submit V1 for review
    v1, audit1 = await service.submit_for_review(
        curriculum_id=v1.id,
        actor_id="admin-1",
        actor_email="admin1@nuc.edu.ng",
        notes="Initial national baseline submission.",
    )
    assert v1.status == BenchmarkStatus.UNDER_REVIEW
    assert audit1.action == BenchmarkAuditAction.SUBMIT_REVIEW

    # Approve V1
    v1, audit2 = await service.approve_curriculum(
        curriculum_id=v1.id,
        reviewer_id="reviewer-lead",
        reviewer_email="lead@nuc.edu.ng",
        reason="Approved national baseline for Computing.",
    )
    assert v1.status == BenchmarkStatus.APPROVED
    assert audit2.action == BenchmarkAuditAction.APPROVE

    # Activate V1
    activated_v1, superseded = await service.activate_curriculum(
        curriculum_id=v1.id,
        activated_by="admin-1",
    )
    assert activated_v1.status == BenchmarkStatus.ACTIVE
    assert superseded is None

    # Check V1 audit trail
    v1_trail = await service.get_audit_trail(v1.id)
    assert len(v1_trail) == 3
    assert [a.action for a in v1_trail] == [
        BenchmarkAuditAction.SUBMIT_REVIEW,
        BenchmarkAuditAction.APPROVE,
        BenchmarkAuditAction.ACTIVATE,
    ]

    # 2. Ingest V2 (modified)
    mod_course = BenchmarkCourseInput(
        code="CSC101",
        title="Intro to CS",
        credit_units=4,  # modified
        level=100,
        semester=1,
        sequence=1,
        topics=[
            BenchmarkTopicInput(
                sequence=1,
                title="Hardware & Microarchitecture",
                outcomes=[
                    BenchmarkOutcomeInput(
                        sequence=1,
                        description="Analyze CPU instruction cycles.",
                        bloom_level="analyze",
                    )
                ],
            )
        ],
    )
    v2, _ = await service.ingest_candidate(
        source_snapshot_id=snap2.id,
        extractor_version="v1.1",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC_GOV",
        version="2026.02",
        minimum_credit_units=4,
        courses=[mod_course],
    )
    await service.validate_candidate(v2.id)

    # Submit V2 for review -> Must automatically attach diff fingerprint against V1
    v2, v2_audit_submit = await service.submit_for_review(
        curriculum_id=v2.id,
        actor_id="admin-2",
        actor_email="admin2@nuc.edu.ng",
        notes="Updated 2026.02 revision with credit change.",
    )
    assert v2.status == BenchmarkStatus.UNDER_REVIEW
    assert v2_audit_submit.diff_fingerprint is not None
    assert len(v2_audit_submit.diff_fingerprint) == 64
    assert v2.review_fingerprint == v2_audit_submit.diff_fingerprint

    # Approve V2
    v2, v2_audit_appr = await service.approve_curriculum(
        curriculum_id=v2.id,
        reviewer_id="reviewer-lead",
        reviewer_email="lead@nuc.edu.ng",
        reason="Approved revised credits.",
    )
    assert v2.status == BenchmarkStatus.APPROVED
    assert v2_audit_appr.diff_fingerprint == v2_audit_submit.diff_fingerprint

    # Activate V2 -> Supersedes V1
    activated_v2, superseded_v1 = await service.activate_curriculum(
        curriculum_id=v2.id,
        activated_by="admin-2",
    )
    assert activated_v2.status == BenchmarkStatus.ACTIVE
    assert superseded_v1 is not None
    assert superseded_v1.id == v1.id
    assert superseded_v1.status == BenchmarkStatus.SUPERSEDED

    # Check V1 audit trail now includes SUPERSEDE
    v1_updated_trail = await service.get_audit_trail(v1.id)
    assert len(v1_updated_trail) == 4
    assert v1_updated_trail[-1].action == BenchmarkAuditAction.SUPERSEDE

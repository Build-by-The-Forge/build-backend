from datetime import datetime, timezone

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
from app.application.curriculum.institutional_adoption_service import (
    InstitutionalAdoptionService,
)
from app.domain.curriculum.adoption import OverrideType
from app.domain.curriculum.effective import EntityOrigin
from app.domain.curriculum.source import CurriculumSource
from app.events.event_bus import EventBus
from app.infrastructure.curriculum.adoption_repositories import (
    SqlAlchemyInstitutionalAdoptionRepository,
)
from app.infrastructure.curriculum.audit_repositories import (
    SqlAlchemyBenchmarkAuditRepository,
)
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)
from app.infrastructure.db.models.tenant_core import TenantModel


@pytest.mark.asyncio
async def test_effective_curriculum_application_resolution(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    audit_repo = SqlAlchemyBenchmarkAuditRepository(session)
    adoption_repo = SqlAlchemyInstitutionalAdoptionRepository(session)
    event_bus = EventBus()

    # 1. Setup Tenant
    now = datetime.now(timezone.utc)
    tenant = TenantModel(
        id="tenant-futa-eff",
        name="FUTA",
        slug="futa-eff",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(tenant)
    await session.flush()

    # 2. Setup Benchmark
    source = CurriculumSource.create(
        code="NUC_EFF_SRC",
        name="CCMAS Effective Resolution Source",
        base_url="https://ccmas.nuc.edu.ng",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://ccmas.nuc.edu.ng/spec.pdf",
        content_sha256="5" * 64,
        raw_artifact_uri="s3://build/spec.pdf",
    )
    await source_repo.save_snapshot(snap)

    benchmark_service = BenchmarkCurriculumService(
        repository=benchmark_repo,
        audit_repository=audit_repo,
        event_bus=event_bus,
    )
    bm, _ = await benchmark_service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=2,
        courses=[
            BenchmarkCourseInput(
                code="CSC101",
                title="Intro to CS",
                credit_units=2,
                level=100,
                semester=1,
                sequence=1,
                topics=[
                    BenchmarkTopicInput(
                        sequence=1,
                        title="Basics",
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
        ],
    )
    await benchmark_service.validate_candidate(bm.id)
    await benchmark_service.submit_for_review(bm.id, actor_id="nuc-admin", actor_email="admin@nuc.edu.ng")
    await benchmark_service.approve_curriculum(
        bm.id,
        reviewer_id="nuc-lead",
        reviewer_email="lead@nuc.edu.ng",
        reason="Approved",
    )
    await benchmark_service.activate_curriculum(bm.id, activated_by="nuc-admin")

    # 3. FUTA Adoption
    adoption_service = InstitutionalAdoptionService(
        adoption_repository=adoption_repo,
        benchmark_repository=benchmark_repo,
        event_bus=event_bus,
    )
    adoption = await adoption_service.adopt_benchmark(
        tenant_id=tenant.id,
        programme_id="prog-csc",
        benchmark_curriculum_id=bm.id,
        academic_session_id="2026-2027",
        actor_id="futa-admin",
        actor_email="admin@futa.edu.ng",
    )

    # 4. Add modification override
    await adoption_service.add_override(
        adoption_id=adoption.id,
        tenant_id=tenant.id,
        override_type=OverrideType.MODIFY_COURSE,
        target_course_code="CSC101",
        field_overrides={"credit_units": 3},
        reason="Senate lab requirement",
        actor_id="futa-admin",
        actor_email="admin@futa.edu.ng",
    )

    # 5. Add custom course
    await adoption_service.add_override(
        adoption_id=adoption.id,
        tenant_id=tenant.id,
        override_type=OverrideType.ADD_COURSE,
        reason="FUTA General Studies",
        custom_payload={
            "code": "GNS101",
            "title": "Use of English",
            "credit_units": 2,
            "level": 100,
            "semester": 1,
            "sequence": 0,
        },
        actor_id="futa-admin",
        actor_email="admin@futa.edu.ng",
    )

    # 6. Activate adoption
    await adoption_service.activate_adoption(
        adoption_id=adoption.id,
        tenant_id=tenant.id,
        actor_id="futa-admin",
    )

    # 7. Query Effective Curriculum by Adoption ID
    effective_by_id = await adoption_service.get_effective_curriculum(
        adoption_id=adoption.id,
        tenant_id=tenant.id,
    )
    assert effective_by_id.statistics.total_courses == 2
    assert effective_by_id.statistics.total_credit_units == 5  # 3 (CSC101) + 2 (GNS101)
    assert effective_by_id.statistics.modified_courses_count == 1
    assert effective_by_id.statistics.custom_courses_count == 1
    assert len(effective_by_id.effective_curriculum_fingerprint) == 64

    # 8. Query Active Effective Curriculum by Programme & Session
    active_effective = await adoption_service.get_active_effective_curriculum(
        tenant_id=tenant.id,
        programme_id="prog-csc",
        academic_session_id="2026-2027",
    )
    assert active_effective.effective_curriculum_fingerprint == effective_by_id.effective_curriculum_fingerprint
    assert active_effective.courses[0].code == "GNS101"  # sequence 0 comes before sequence 1
    assert active_effective.courses[0].origin == EntityOrigin.INSTITUTIONAL_CUSTOM
    assert active_effective.courses[1].code == "CSC101"
    assert active_effective.courses[1].origin == EntityOrigin.INSTITUTIONAL_MODIFIED
    assert active_effective.courses[1].credit_units == 3

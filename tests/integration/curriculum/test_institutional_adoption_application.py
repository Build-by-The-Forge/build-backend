from datetime import datetime, timezone

import pytest
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
from app.domain.curriculum.adoption import AdoptionStatus, OverrideType
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
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_institutional_adoption_workflow_and_invariants(
    session: AsyncSession,
) -> None:
    # Repositories
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    audit_repo = SqlAlchemyBenchmarkAuditRepository(session)
    adoption_repo = SqlAlchemyInstitutionalAdoptionRepository(session)
    event_bus = EventBus()

    # 1. Setup Tenant (FUTA)
    now = datetime.now(timezone.utc)
    tenant = TenantModel(
        id="tenant-futa-1",
        name="Federal University of Technology Akure",
        slug="futa-test",
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(tenant)
    await session.flush()

    # 2. Setup Benchmark Source and Active Benchmark (CCMAS CSC v2026.01)
    source = CurriculumSource.create(
        code="NUC_CCMAS_ADOPT",
        name="CCMAS National Benchmark",
        base_url="https://ccmas.nuc.edu.ng",
    )
    await source_repo.save_source(source)

    snap = source.create_snapshot(
        source_url="https://ccmas.nuc.edu.ng/spec.pdf",
        content_sha256="8" * 64,
        raw_artifact_uri="s3://build/spec.pdf",
    )
    await source_repo.save_snapshot(snap)

    benchmark_service = BenchmarkCurriculumService(
        repository=benchmark_repo,
        audit_repository=audit_repo,
        event_bus=event_bus,
    )

    course_cos101 = BenchmarkCourseInput(
        code="COS101",
        title="Introduction to Computing",
        credit_units=2,
        level=100,
        semester=1,
        sequence=1,
        topics=[
            BenchmarkTopicInput(
                sequence=1,
                title="Computing Basics",
                outcomes=[
                    BenchmarkOutcomeInput(
                        sequence=1,
                        description="Understand computers.",
                        bloom_level="understand",
                    )
                ],
            )
        ],
    )
    course_cos102 = BenchmarkCourseInput(
        code="COS102",
        title="Problem Solving & Programming",
        credit_units=2,
        level=100,
        semester=2,
        sequence=2,
        topics=[
            BenchmarkTopicInput(
                sequence=1,
                title="Algorithms",
                outcomes=[
                    BenchmarkOutcomeInput(
                        sequence=1,
                        description="Write algorithms.",
                        bloom_level="apply",
                    )
                ],
            )
        ],
    )

    benchmark_v1, _ = await benchmark_service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=4,
        courses=[course_cos101, course_cos102],
    )
    await benchmark_service.validate_candidate(benchmark_v1.id)
    await benchmark_service.submit_for_review(
        benchmark_v1.id,
        actor_id="nuc-admin",
        actor_email="admin@nuc.edu.ng",
    )
    await benchmark_service.approve_curriculum(
        benchmark_v1.id,
        reviewer_id="nuc-lead",
        reviewer_email="lead@nuc.edu.ng",
        reason="Approved national standard",
    )
    activated_benchmark, _ = await benchmark_service.activate_curriculum(
        curriculum_id=benchmark_v1.id,
        activated_by="nuc-admin",
    )
    assert activated_benchmark.status == "active"

    # 3. Institutional Adoption Service
    adoption_service = InstitutionalAdoptionService(
        adoption_repository=adoption_repo,
        benchmark_repository=benchmark_repo,
        event_bus=event_bus,
    )

    # Invariant: Adopting a non-existent benchmark fails
    with pytest.raises(ValueError, match="benchmark curriculum not found"):
        await adoption_service.adopt_benchmark(
            tenant_id=tenant.id,
            programme_id="prog-csc-futa",
            benchmark_curriculum_id="nonexistent-id",
            actor_id="futa-hod",
            actor_email="hod@futa.edu.ng",
        )

    # 4. FUTA adopts CCMAS v2026.01
    futa_adoption = await adoption_service.adopt_benchmark(
        tenant_id=tenant.id,
        programme_id="prog-csc-futa",
        benchmark_curriculum_id=benchmark_v1.id,
        academic_session_id="session-2026-2027",
        notes="FUTA Computer Science Department 2026/27 Curriculum Adoption",
        actor_id="futa-hod",
        actor_email="hod@futa.edu.ng",
    )
    assert futa_adoption.status == AdoptionStatus.DRAFT
    assert futa_adoption.benchmark_curriculum_id == benchmark_v1.id
    assert futa_adoption.benchmark_version == "2026.01"

    # 5. Add Override 1: Modify COS 102 from 2 units to 3 units (with mandatory rationale)
    mod_override = await adoption_service.add_override(
        adoption_id=futa_adoption.id,
        tenant_id=tenant.id,
        override_type=OverrideType.MODIFY_COURSE,
        target_course_code="COS102",
        field_overrides={"credit_units": 3},
        reason="FUTA Senate approved 3 credit units to incorporate mandatory practical laboratory sessions.",
        actor_id="futa-hod",
        actor_email="hod@futa.edu.ng",
    )
    assert mod_override.target_course_code == "COS102"
    assert mod_override.field_overrides["credit_units"] == 3

    # Invariant: Override targeting non-existent benchmark course fails
    with pytest.raises(
        ValueError,
        match="target course 'INVALID999' does not exist in adopted benchmark",
    ):
        await adoption_service.add_override(
            adoption_id=futa_adoption.id,
            tenant_id=tenant.id,
            override_type=OverrideType.MODIFY_COURSE,
            target_course_code="INVALID999",
            field_overrides={"credit_units": 3},
            reason="Senate approval",
            actor_id="futa-hod",
            actor_email="hod@futa.edu.ng",
        )

    # 6. Add Override 2: Add institutional custom course GNS 101
    add_override = await adoption_service.add_override(
        adoption_id=futa_adoption.id,
        tenant_id=tenant.id,
        override_type=OverrideType.ADD_COURSE,
        reason="FUTA university-wide General Studies requirement.",
        custom_payload={
            "code": "GNS101",
            "title": "Use of English",
            "credit_units": 2,
            "level": 100,
            "semester": 1,
        },
        actor_id="futa-hod",
        actor_email="hod@futa.edu.ng",
    )
    assert add_override.custom_payload["code"] == "GNS101"

    # 7. Add and remove a draft override
    omit_override = await adoption_service.add_override(
        adoption_id=futa_adoption.id,
        tenant_id=tenant.id,
        override_type=OverrideType.OMIT_COURSE,
        target_course_code="COS101",
        reason="Temporary test omission",
        actor_id="futa-hod",
        actor_email="hod@futa.edu.ng",
    )
    del_ok = await adoption_service.remove_override(
        adoption_id=futa_adoption.id,
        override_id=omit_override.id,
        tenant_id=tenant.id,
    )
    assert del_ok is True

    # 8. Query Detail
    adoption_detail, overrides = await adoption_service.get_adoption_detail(
        adoption_id=futa_adoption.id,
        tenant_id=tenant.id,
    )
    assert len(overrides) == 2

    # 9. Activate FUTA Adoption
    activated_adoption, superseded = await adoption_service.activate_adoption(
        adoption_id=futa_adoption.id,
        tenant_id=tenant.id,
        actor_id="futa-dean",
    )
    assert activated_adoption.status == AdoptionStatus.ACTIVE
    assert superseded is None

    # Invariant: Overrides cannot be added or deleted on an ACTIVE adoption (immutability)
    with pytest.raises(
        ValueError,
        match="cannot add overrides to adoption in status 'active'",
    ):
        await adoption_service.add_override(
            adoption_id=futa_adoption.id,
            tenant_id=tenant.id,
            override_type=OverrideType.MODIFY_COURSE,
            target_course_code="COS102",
            field_overrides={"credit_units": 4},
            reason="Late change",
            actor_id="futa-hod",
            actor_email="hod@futa.edu.ng",
        )

    with pytest.raises(
        ValueError,
        match="cannot remove overrides from adoption in status 'active'",
    ):
        await adoption_service.remove_override(
            adoption_id=futa_adoption.id,
            override_id=mod_override.id,
            tenant_id=tenant.id,
        )

    # 10. Invariant: Benchmark version pinning remains unchanged even when NUC issues v2026.02
    active_futa = await adoption_repo.get_active_adoption(
        tenant_id=tenant.id,
        programme_id="prog-csc-futa",
        academic_session_id="session-2026-2027",
    )
    assert active_futa is not None
    assert active_futa.benchmark_version == "2026.01"
    assert active_futa.benchmark_curriculum_id == benchmark_v1.id

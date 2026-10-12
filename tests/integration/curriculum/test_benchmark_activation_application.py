import pytest
from app.application.curriculum.benchmark_commands import (
    BenchmarkCourseInput,
    BenchmarkOutcomeInput,
    BenchmarkTopicInput,
)
from app.application.curriculum.benchmark_service import (
    BenchmarkCurriculumService,
)
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
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_benchmark_activation_and_supersession_pipeline(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    audit_repo = SqlAlchemyBenchmarkAuditRepository(session)
    event_bus = EventBus()
    events_emitted: list[str] = []

    event_bus.subscribe(
        "curriculum.benchmark_activated",
        lambda e: events_emitted.append("activated"),
    )
    event_bus.subscribe(
        "curriculum.benchmark_superseded",
        lambda e: events_emitted.append("superseded"),
    )

    source = CurriculumSource.create(
        code="NUC_ACT_TEST",
        name="Activation Test Source",
        base_url="https://act.example.com",
    )
    await source_repo.save_source(source)

    snap1 = source.create_snapshot(
        source_url="https://act.example.com/v1.pdf",
        content_sha256="1" * 64,
        raw_artifact_uri="s3://build/v1.pdf",
    )
    await source_repo.save_snapshot(snap1)

    snap2 = source.create_snapshot(
        source_url="https://act.example.com/v2.pdf",
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
                title="Von Neumann",
                description="Hardware",
                outcomes=[
                    BenchmarkOutcomeInput(
                        sequence=1,
                        description="Explain CPU architecture.",
                        bloom_level="understand",
                    )
                ],
            )
        ],
    )

    # 1. Ingest V1
    v1_curr, _ = await service.ingest_candidate(
        source_snapshot_id=snap1.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=3,
        courses=[course_input],
    )
    await service.validate_candidate(v1_curr.id)
    await service.submit_for_review(v1_curr.id, actor_id="admin-1", actor_email="admin1@nuc.edu.ng")
    await service.approve_curriculum(
        v1_curr.id,
        reviewer_id="rev-1",
        reviewer_email="rev1@nuc.edu.ng",
        reason="Approved v1",
    )

    # 2. Activate V1 -> Becomes ACTIVE, 0 superseded
    activated_v1, superseded = await service.activate_curriculum(
        curriculum_id=v1_curr.id,
        activated_by="admin-1",
    )
    assert activated_v1.status == BenchmarkStatus.ACTIVE
    assert superseded is None
    assert "activated" in events_emitted

    # Active lookup returns V1
    active_res = await service.get_active_curriculum(
        discipline_group="Computing",
        programme_code="CSC",
        degree_level="undergraduate",
    )
    assert active_res is not None
    assert active_res.id == v1_curr.id
    assert active_res.version == "2026.01"

    # 3. Ingest V2 (from snap2)
    v2_curr, _ = await service.ingest_candidate(
        source_snapshot_id=snap2.id,
        extractor_version="v1.1",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.02",
        minimum_credit_units=3,
        courses=[course_input],
    )
    await service.validate_candidate(v2_curr.id)
    await service.submit_for_review(v2_curr.id, actor_id="admin-1", actor_email="admin1@nuc.edu.ng")
    await service.approve_curriculum(
        v2_curr.id,
        reviewer_id="rev-1",
        reviewer_email="rev1@nuc.edu.ng",
        reason="Approved v2",
    )

    # 4. Activate V2 -> V2 becomes ACTIVE, V1 becomes SUPERSEDED
    activated_v2, superseded_v1 = await service.activate_curriculum(
        curriculum_id=v2_curr.id,
        activated_by="admin-1",
    )
    assert activated_v2.status == BenchmarkStatus.ACTIVE
    assert activated_v2.version == "2026.02"
    assert superseded_v1 is not None
    assert superseded_v1.id == v1_curr.id
    assert superseded_v1.status == BenchmarkStatus.SUPERSEDED
    assert "superseded" in events_emitted

    # 5. Query active benchmark -> Returns V2
    active_now = await service.get_active_curriculum(
        discipline_group="Computing",
        programme_code="CSC",
        degree_level="undergraduate",
    )
    assert active_now is not None
    assert active_now.id == v2_curr.id
    assert active_now.version == "2026.02"

    # 6. Verify V1 in DB is SUPERSEDED, not deleted
    refreshed_v1 = await benchmark_repo.get_by_id(v1_curr.id)
    assert refreshed_v1 is not None
    assert refreshed_v1.status == BenchmarkStatus.SUPERSEDED

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
from app.domain.curriculum.benchmark import BenchmarkStatus
from app.domain.curriculum.source import CurriculumSource
from app.events.event_bus import EventBus
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)


@pytest.mark.asyncio
async def test_validate_candidate_application_success(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    event_bus = EventBus()
    events_emitted: list[str] = []

    event_bus.subscribe(
        "curriculum.benchmark_validated",
        lambda e: events_emitted.append(getattr(e, "event_type", "")),
    )

    source = CurriculumSource.create(
        code="NUC_VAL_TEST",
        name="Validation Test",
        base_url="https://val.example.com",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://val.example.com/csc.pdf",
        content_sha256="6" * 64,
        raw_artifact_uri="s3://build/csc.pdf",
    )
    await source_repo.save_snapshot(snap)

    service = BenchmarkCurriculumService(
        repository=benchmark_repo,
        event_bus=event_bus,
    )

    # 1. Ingest clean candidate
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
                description="Architecture",
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

    curriculum, _ = await service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC_VAL",
        version="2026.01",
        minimum_credit_units=3,
        courses=[course_input],
    )
    assert curriculum.status == BenchmarkStatus.CANDIDATE

    # 2. Validate Candidate
    validated_curr, result = await service.validate_candidate(curriculum.id)

    assert result.is_valid is True
    assert result.error_count == 0
    assert validated_curr.status == BenchmarkStatus.VALIDATED
    assert "curriculum.benchmark_validated" in events_emitted

    # 3. Check persisted status in DB
    refreshed = await benchmark_repo.get_by_id(curriculum.id)
    assert refreshed is not None
    assert refreshed.status == BenchmarkStatus.VALIDATED

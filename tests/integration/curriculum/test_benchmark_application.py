import pytest
from app.application.curriculum.benchmark_commands import (
    BenchmarkCourseInput,
    BenchmarkOutcomeInput,
    BenchmarkTopicInput,
)
from app.application.curriculum.benchmark_service import (
    BenchmarkCurriculumService,
)
from app.domain.curriculum.source import CurriculumSource
from app.events.event_bus import EventBus
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_ingest_benchmark_candidate_and_retrieval(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    event_bus = EventBus()
    events_emitted: list[str] = []

    event_bus.subscribe(
        "curriculum.benchmark_candidate_created",
        lambda e: events_emitted.append(getattr(e, "event_type", "")),
    )

    source = CurriculumSource.create(
        code="NUC_CCMAS_INGEST_APP",
        name="Ingest App Source",
        base_url="https://ccmas.example.com",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://ccmas.example.com/csc.pdf",
        content_sha256="9" * 64,
        raw_artifact_uri="s3://build/csc.pdf",
    )
    await source_repo.save_snapshot(snap)

    service = BenchmarkCurriculumService(
        repository=benchmark_repo,
        event_bus=event_bus,
    )

    course_input = BenchmarkCourseInput(
        code="COS101",
        title="Introduction to Computer Science",
        credit_units=3,
        level=100,
        semester=1,
        sequence=1,
        topics=[
            BenchmarkTopicInput(
                sequence=1,
                title="Von Neumann Architecture",
                description="Components of computers",
                outcomes=[
                    BenchmarkOutcomeInput(
                        sequence=1,
                        description="Identify CPU, ALU, Registers, and Memory.",
                        bloom_level="remember",
                    )
                ],
            )
        ],
    )

    # 1. Ingest Candidate
    curriculum, created = await service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.2-gemini",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=120,
        courses=[course_input],
    )

    assert created is True
    assert curriculum.programme_code == "CSC"
    assert "curriculum.benchmark_candidate_created" in events_emitted

    # 2. Re-ingest exact same snapshot + programme -> Idempotent no-op
    curr_repeat, created_repeat = await service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.2-gemini",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=120,
        courses=[course_input],
    )
    assert created_repeat is False
    assert curr_repeat.id == curriculum.id

    # 3. Retrieve Courses via service
    courses = await service.list_courses(curriculum.id, level=100, semester=1)
    assert len(courses) == 1
    assert courses[0].code == "COS101"

    # 4. Retrieve Full Course Tree
    course_detail = await service.get_course(courses[0].id)
    assert course_detail is not None
    assert len(course_detail.topics) == 1
    assert len(course_detail.topics[0].outcomes) == 1
    assert course_detail.topics[0].outcomes[0].description == "Identify CPU, ALU, Registers, and Memory."


@pytest.mark.asyncio
async def test_ingest_duplicate_course_code_rejected(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)

    source = CurriculumSource.create(
        code="NUC_DUP_COURSE_APP",
        name="Dup Course App",
        base_url="https://ccmas.example.com",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://ccmas.example.com/csc.pdf",
        content_sha256="8" * 64,
        raw_artifact_uri="s3://build/csc.pdf",
    )
    await source_repo.save_snapshot(snap)

    service = BenchmarkCurriculumService(repository=benchmark_repo)

    duplicate_courses = [
        BenchmarkCourseInput(
            code="CSC101",
            title="Course 1",
            credit_units=3,
            level=100,
            semester=1,
            sequence=1,
        ),
        BenchmarkCourseInput(
            code="CSC101",
            title="Course 2",
            credit_units=3,
            level=100,
            semester=1,
            sequence=2,
        ),
    ]

    with pytest.raises(ValueError, match="duplicate course code 'CSC101' in candidate payload"):
        await service.ingest_candidate(
            source_snapshot_id=snap.id,
            extractor_version="v1.2",
            discipline_group="Computing",
            programme_name="Computer Science",
            programme_code="CSC_DUP",
            version="2026.01",
            courses=duplicate_courses,
        )

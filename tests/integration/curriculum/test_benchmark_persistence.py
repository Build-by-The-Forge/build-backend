import pytest
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkStatus,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)
from app.domain.curriculum.source import CurriculumSource
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_benchmark_curriculum_persistence_round_trip(
    session: AsyncSession,
) -> None:
    # 1. Seed Source and Snapshot
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    source = CurriculumSource.create(
        code="NUC_CCMAS_BM_TEST",
        name="CCMAS Test Source",
        base_url="https://ccmas.example.com",
    )
    await source_repo.save_source(source)

    snap = source.create_snapshot(
        source_url="https://ccmas.example.com/csc.pdf",
        content_sha256="c" * 64,
        raw_artifact_uri="s3://build-artifacts/ccmas/csc.pdf",
    )
    await source_repo.save_snapshot(snap)

    # 2. Persist Benchmark Curriculum Header
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    curriculum = BenchmarkCurriculum.create_candidate(
        source_snapshot_id=snap.id,
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=120,
    )
    await benchmark_repo.save(curriculum)

    retrieved = await benchmark_repo.get_by_id(curriculum.id)
    assert retrieved is not None
    assert retrieved.programme_code == "CSC"
    assert retrieved.discipline_group == "Computing"
    assert retrieved.status == BenchmarkStatus.CANDIDATE

    retrieved_by_snap = await benchmark_repo.get_by_snapshot_and_programme(
        snap.id, "CSC"
    )
    assert retrieved_by_snap is not None
    assert retrieved_by_snap.id == curriculum.id


@pytest.mark.asyncio
async def test_benchmark_course_tree_persistence_and_filtering(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    source = CurriculumSource.create(
        code="NUC_CCMAS_TREE_TEST",
        name="Tree Test",
        base_url="https://tree.example.com",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://tree.example.com/spec.pdf",
        content_sha256="d" * 64,
        raw_artifact_uri="s3://path",
    )
    await source_repo.save_snapshot(snap)

    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    curriculum = BenchmarkCurriculum.create_candidate(
        source_snapshot_id=snap.id,
        discipline_group="Computing",
        programme_name="Software Engineering",
        programme_code="SEN",
        version="2026.01",
    )
    await benchmark_repo.save(curriculum)

    # Add Course 1 (Level 100, Sem 1)
    c1 = BenchmarkCourse.create(
        benchmark_curriculum_id=curriculum.id,
        code="SEN101",
        title="Introduction to Software Engineering",
        credit_units=3,
        level=100,
        semester=1,
        sequence=1,
    )
    t1 = BenchmarkTopic.create(
        benchmark_course_id=c1.id,
        sequence=1,
        title="Software Lifecycle Models",
    )
    o1 = BenchmarkOutcome.create(
        benchmark_topic_id=t1.id,
        sequence=1,
        description="Explain the phases of the Waterfall and Agile lifecycles.",
        bloom_level=BloomTaxonomyLevel.UNDERSTAND,
    )
    t1.add_outcome(o1)
    c1.add_topic(t1)
    await benchmark_repo.save_course(c1)

    # Add Course 2 (Level 200, Sem 1)
    c2 = BenchmarkCourse.create(
        benchmark_curriculum_id=curriculum.id,
        code="SEN201",
        title="Software Requirements Engineering",
        credit_units=3,
        level=200,
        semester=1,
        sequence=2,
    )
    await benchmark_repo.save_course(c2)

    # Query individual course with nested topics and outcomes
    retrieved_c1 = await benchmark_repo.get_course(c1.id)
    assert retrieved_c1 is not None
    assert retrieved_c1.code == "SEN101"
    assert len(retrieved_c1.topics) == 1
    assert retrieved_c1.topics[0].title == "Software Lifecycle Models"
    assert len(retrieved_c1.topics[0].outcomes) == 1
    assert (
        retrieved_c1.topics[0].outcomes[0].bloom_level == BloomTaxonomyLevel.UNDERSTAND
    )

    # List all courses
    all_courses = await benchmark_repo.list_courses(curriculum.id)
    assert len(all_courses) == 2
    assert all_courses[0].code == "SEN101"
    assert all_courses[1].code == "SEN201"

    # Filter courses by level
    lvl100_courses = await benchmark_repo.list_courses(
        curriculum.id, level=100, semester=1
    )
    assert len(lvl100_courses) == 1
    assert lvl100_courses[0].code == "SEN101"


@pytest.mark.asyncio
async def test_duplicate_snapshot_and_programme_constraint(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    source = CurriculumSource.create(
        code="NUC_DUP_TEST",
        name="Dup Test",
        base_url="https://dup.example.com",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://dup.example.com/spec.pdf",
        content_sha256="b" * 64,
        raw_artifact_uri="s3://path",
    )
    await source_repo.save_snapshot(snap)

    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)
    curr1 = BenchmarkCurriculum.create_candidate(
        source_snapshot_id=snap.id,
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
    )
    await benchmark_repo.save(curr1)

    curr2 = BenchmarkCurriculum.create_candidate(
        source_snapshot_id=snap.id,
        discipline_group="Computing",
        programme_name="Computer Science Duplicate",
        programme_code="CSC",
        version="2026.01",
    )
    with pytest.raises(IntegrityError):
        await benchmark_repo.save(curr2)

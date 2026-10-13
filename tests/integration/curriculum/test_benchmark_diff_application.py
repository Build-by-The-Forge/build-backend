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
from app.domain.curriculum.diff import DiffAction
from app.domain.curriculum.source import CurriculumSource
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import (
    SqlAlchemyCurriculumSourceRepository,
)


@pytest.mark.asyncio
async def test_compare_curricula_application_service(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)

    source = CurriculumSource.create(
        code="NUC_DIFF_TEST",
        name="Diff Test Source",
        base_url="https://diff.example.com",
    )
    await source_repo.save_source(source)

    snap1 = source.create_snapshot(
        source_url="https://diff.example.com/v1.pdf",
        content_sha256="a" * 64,
        raw_artifact_uri="s3://build/v1.pdf",
    )
    await source_repo.save_snapshot(snap1)

    snap2 = source.create_snapshot(
        source_url="https://diff.example.com/v2.pdf",
        content_sha256="b" * 64,
        raw_artifact_uri="s3://build/v2.pdf",
    )
    await source_repo.save_snapshot(snap2)

    service = BenchmarkCurriculumService(repository=benchmark_repo)

    # 1. Ingest V1 (COS101, COS102)
    v1_courses = [
        BenchmarkCourseInput(
            code="COS101",
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
                            description="Explain CPU registers.",
                            bloom_level="understand",
                        )
                    ],
                )
            ],
        ),
        BenchmarkCourseInput(
            code="COS102",
            title="Programming in C",
            credit_units=2,
            level=100,
            semester=2,
            sequence=2,
        ),
    ]

    v1, _ = await service.ingest_candidate(
        source_snapshot_id=snap1.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC_DIFF",
        version="2026.01",
        courses=v1_courses,
    )

    # 2. Ingest V2 (COS101 modified to 4 credits, COS102 removed, COS103 added)
    v2_courses = [
        BenchmarkCourseInput(
            code="COS101",
            title="Intro to CS",
            credit_units=4,  # modified 3 -> 4
            level=100,
            semester=1,
            sequence=1,
            topics=[
                BenchmarkTopicInput(
                    sequence=1,
                    title="Hardware & Architectures",  # modified title
                    outcomes=[
                        BenchmarkOutcomeInput(
                            sequence=1,
                            description="Explain CPU registers and pipeline.",
                            bloom_level="analyze",  # modified bloom
                        )
                    ],
                )
            ],
        ),
        BenchmarkCourseInput(
            code="COS103",
            title="Discrete Mathematics",
            credit_units=3,
            level=100,
            semester=1,
            sequence=2,
        ),
    ]

    v2, _ = await service.ingest_candidate(
        source_snapshot_id=snap2.id,
        extractor_version="v1.1",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC_DIFF",
        version="2026.02",
        courses=v2_courses,
    )

    # 3. Compare V1 and V2
    diff = await service.compare_curricula(
        source_curriculum_id=v1.id,
        target_curriculum_id=v2.id,
    )

    assert diff.source_version == "2026.01"
    assert diff.target_version == "2026.02"
    assert diff.statistics.courses_added == 1
    assert diff.statistics.courses_removed == 1
    assert diff.statistics.courses_modified == 1
    assert diff.statistics.credit_units_before == 5
    assert diff.statistics.credit_units_after == 7
    assert diff.statistics.credit_units_delta == 2
    assert len(diff.diff_fingerprint) == 64

    diff_map = {c.code: c for c in diff.course_diffs}
    assert diff_map["COS101"].action == DiffAction.MODIFIED
    assert diff_map["COS102"].action == DiffAction.REMOVED
    assert diff_map["COS103"].action == DiffAction.ADDED


@pytest.mark.asyncio
async def test_compare_different_programmes_raises_error(
    session: AsyncSession,
) -> None:
    source_repo = SqlAlchemyCurriculumSourceRepository(session)
    benchmark_repo = SqlAlchemyBenchmarkCurriculumRepository(session)

    source = CurriculumSource.create(
        code="NUC_MISMATCH",
        name="Mismatch",
        base_url="https://diff.example.com",
    )
    await source_repo.save_source(source)
    snap = source.create_snapshot(
        source_url="https://diff.example.com/spec.pdf",
        content_sha256="c" * 64,
        raw_artifact_uri="s3://build/spec.pdf",
    )
    await source_repo.save_snapshot(snap)

    service = BenchmarkCurriculumService(repository=benchmark_repo)

    c1, _ = await service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC_A",
        version="2026.01",
    )
    c2, _ = await service.ingest_candidate(
        source_snapshot_id=snap.id,
        extractor_version="v1.0",
        discipline_group="Computing",
        programme_name="Software Engineering",
        programme_code="SEN_B",
        version="2026.01",
    )

    with pytest.raises(ValueError, match="cannot compare curricula of different programmes"):
        await service.compare_curricula(c1.id, c2.id)

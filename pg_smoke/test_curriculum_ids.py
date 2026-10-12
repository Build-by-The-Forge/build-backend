"""Curriculum aggregates persist with their generated ids on PostgreSQL.

The ids the domain generates by default must fit the id columns. SQLite does
not enforce VARCHAR lengths, so only PostgreSQL catches a mismatch (as it did
for content and curriculum ids, which were prefixed and longer than 36).
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.domain.curriculum.adoption import CurriculumOverride, InstitutionalAdoption, OverrideType
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkTopic,
)
from app.domain.curriculum.source import CurriculumSource
from app.infrastructure.curriculum.adoption_repositories import (
    SqlAlchemyInstitutionalAdoptionRepository,
)
from app.infrastructure.curriculum.benchmark_repositories import (
    SqlAlchemyBenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.repositories import SqlAlchemyCurriculumSourceRepository
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    ProgrammeModel,
    TenantModel,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _programme(session) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    tenant, faculty, department, programme = (str(uuid4()) for _ in range(4))
    tag = uuid4().hex[:8]
    session.add(TenantModel(id=tenant, name="Ids", slug=f"ids-{tag}", status="active", created_at=now, updated_at=now))
    await session.flush()
    session.add(
        FacultyModel(id=faculty, tenant_id=tenant, name="F", slug=f"f-{tag}", status="active", created_at=now, updated_at=now)
    )
    await session.flush()
    session.add(
        DepartmentModel(
            id=department,
            tenant_id=tenant,
            faculty_id=faculty,
            name="D",
            slug=f"d-{tag}",
            code=f"D{tag[:6].upper()}",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    session.add(
        ProgrammeModel(
            id=programme,
            tenant_id=tenant,
            faculty_id=faculty,
            department_id=department,
            name="P",
            slug=f"p-{tag}",
            code=f"P{tag[:6].upper()}",
            duration_years=5,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    return tenant, programme


async def test_every_curriculum_aggregate_persists_with_its_generated_id():
    async with SessionLocal() as session:
        sources = SqlAlchemyCurriculumSourceRepository(session)
        benchmarks = SqlAlchemyBenchmarkCurriculumRepository(session)
        adoptions = SqlAlchemyInstitutionalAdoptionRepository(session)

        source = CurriculumSource.create(code=f"SRC{uuid4().hex[:6]}", name="Benchmark", base_url="https://example.org")
        await sources.save_source(source)
        snapshot = source.create_snapshot(
            source_url="https://example.org/ccmas.pdf",
            content_sha256="a" * 64,
            raw_artifact_uri="s3://snapshots/ccmas.pdf",
        )
        await sources.save_snapshot(snapshot)

        curriculum = BenchmarkCurriculum.create_candidate(
            source_snapshot_id=snapshot.id,
            discipline_group="Computing",
            programme_name="Computer Science",
            programme_code=f"CSC{uuid4().hex[:4]}",
            version="2023",
        )
        await benchmarks.save(curriculum)
        course = BenchmarkCourse.create(
            benchmark_curriculum_id=curriculum.id,
            code="CSC101",
            title="Introduction to Computing",
            credit_units=3,
            level=100,
            semester=1,
        )
        topic = BenchmarkTopic.create(benchmark_course_id=course.id, sequence=1, title="Algorithms")
        topic.add_outcome(BenchmarkOutcome.create(benchmark_topic_id=topic.id, sequence=1, description="Define an algorithm"))
        course.add_topic(topic)
        await benchmarks.save_course(course)

        tenant, programme = await _programme(session)
        adoption = InstitutionalAdoption.create_draft(
            tenant_id=tenant,
            programme_id=programme,
            benchmark_curriculum_id=curriculum.id,
            benchmark_version="2023",
            adopted_by=str(uuid4()),
            adopted_by_email="registrar@example.org",
        )
        await adoptions.save_adoption(adoption)
        override = CurriculumOverride.create(
            adoption_id=adoption.id,
            override_type=OverrideType.OMIT_COURSE,
            reason="Not offered",
            created_by=str(uuid4()),
            created_by_email="registrar@example.org",
            target_course_code="CSC101",
        )
        await adoptions.save_override(override)
        await session.commit()

    async with SessionLocal() as session:
        sources = SqlAlchemyCurriculumSourceRepository(session)
        benchmarks = SqlAlchemyBenchmarkCurriculumRepository(session)
        adoptions = SqlAlchemyInstitutionalAdoptionRepository(session)
        assert (await sources.get_source_by_id(source.id)).id == source.id
        assert (await sources.get_latest_snapshot(source.id)).id == snapshot.id
        assert (await benchmarks.get_by_id(curriculum.id)).id == curriculum.id
        stored_course = await benchmarks.get_course(course.id)
        assert stored_course.topics[0].id == topic.id
        assert stored_course.topics[0].outcomes[0].id == topic.outcomes[0].id
        assert (await adoptions.get_adoption_by_id(adoption.id)).id == adoption.id
        assert (await adoptions.get_override(override.id)).id == override.id

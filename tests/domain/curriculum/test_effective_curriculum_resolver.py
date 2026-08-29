import pytest
from app.domain.curriculum.adoption import (
    CurriculumOverride,
    InstitutionalAdoption,
    OverrideType,
)
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)
from app.domain.curriculum.effective import (
    RESOLUTION_ENGINE_VERSION,
    EffectiveCurriculumResolver,
    EntityOrigin,
)


def _sample_benchmark() -> tuple[BenchmarkCurriculum, list[BenchmarkCourse]]:
    curr = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-1",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
    )
    curr.review_fingerprint = "f" * 64

    c1 = BenchmarkCourse.create(
        benchmark_curriculum_id=curr.id,
        code="COS101",
        title="Intro to Computing",
        credit_units=2,
        level=100,
        semester=1,
        sequence=1,
        topics=[
            BenchmarkTopic.create(
                benchmark_course_id="c1",
                sequence=1,
                title="Von Neumann Architecture",
                description="Hardware fundamentals",
                outcomes=[
                    BenchmarkOutcome.create(
                        benchmark_topic_id="t1",
                        sequence=1,
                        description="Explain CPU cycles.",
                        bloom_level=BloomTaxonomyLevel.UNDERSTAND,
                    )
                ],
            )
        ],
    )

    c2 = BenchmarkCourse.create(
        benchmark_curriculum_id=curr.id,
        code="COS102",
        title="Programming Principles",
        credit_units=2,
        level=100,
        semester=2,
        sequence=2,
    )

    c3 = BenchmarkCourse.create(
        benchmark_curriculum_id=curr.id,
        code="CSC201",
        title="Data Structures",
        credit_units=3,
        level=200,
        semester=1,
        sequence=1,
    )

    return curr, [c1, c2, c3]


def test_effective_curriculum_resolver_unmodified_baseline() -> None:
    benchmark, courses = _sample_benchmark()
    adoption = InstitutionalAdoption.create_draft(
        tenant_id="futa",
        programme_id="csc",
        benchmark_curriculum_id=benchmark.id,
        benchmark_version=benchmark.version,
        benchmark_fingerprint=benchmark.review_fingerprint,
        adopted_by="admin-1",
        adopted_by_email="dean@futa.edu.ng",
    )

    resolver = EffectiveCurriculumResolver()
    effective = resolver.resolve(
        adoption=adoption,
        benchmark=benchmark,
        benchmark_courses=courses,
        overrides=[],
    )

    assert effective.resolution_engine_version == RESOLUTION_ENGINE_VERSION
    assert effective.statistics.total_courses == 3
    assert effective.statistics.total_credit_units == 7
    assert effective.statistics.national_courses_count == 3
    assert effective.statistics.modified_courses_count == 0
    assert effective.statistics.custom_courses_count == 0
    assert effective.statistics.omitted_courses_count == 0
    assert len(effective.omitted_courses) == 0
    assert len(effective.effective_curriculum_fingerprint) == 64

    for c in effective.courses:
        assert c.origin == EntityOrigin.NATIONAL_BENCHMARK
        assert len(c.applied_overrides) == 0


def test_effective_curriculum_resolver_with_modifications_additions_and_omissions() -> (
    None
):
    benchmark, courses = _sample_benchmark()
    adoption = InstitutionalAdoption.create_draft(
        tenant_id="futa",
        programme_id="csc",
        benchmark_curriculum_id=benchmark.id,
        benchmark_version=benchmark.version,
        benchmark_fingerprint=benchmark.review_fingerprint,
        adopted_by="admin-1",
        adopted_by_email="dean@futa.edu.ng",
    )

    # 1. Modify COS102 to 3 units
    ov_mod = CurriculumOverride.create(
        adoption_id=adoption.id,
        override_type=OverrideType.MODIFY_COURSE,
        target_course_code="COS102",
        reason="Senate approved 3 units for laboratory component",
        created_by="admin-1",
        created_by_email="dean@futa.edu.ng",
        field_overrides={"credit_units": 3},
    )

    # 2. Add custom course GNS101
    ov_add = CurriculumOverride.create(
        adoption_id=adoption.id,
        override_type=OverrideType.ADD_COURSE,
        reason="FUTA General Studies",
        created_by="admin-1",
        created_by_email="dean@futa.edu.ng",
        custom_payload={
            "code": "GNS101",
            "title": "Use of English",
            "credit_units": 2,
            "level": 100,
            "semester": 1,
            "sequence": 0,
            "topics": [
                {
                    "sequence": 1,
                    "title": "Grammar",
                    "outcomes": [
                        {
                            "sequence": 1,
                            "description": "Construct paragraphs.",
                            "bloom_level": "apply",
                        }
                    ],
                }
            ],
        },
    )

    # 3. Omit CSC201
    ov_omit = CurriculumOverride.create(
        adoption_id=adoption.id,
        override_type=OverrideType.OMIT_COURSE,
        target_course_code="CSC201",
        reason="Omitted in favor of faculty elective",
        created_by="admin-1",
        created_by_email="dean@futa.edu.ng",
    )

    resolver = EffectiveCurriculumResolver()
    effective = resolver.resolve(
        adoption=adoption,
        benchmark=benchmark,
        benchmark_courses=courses,
        overrides=[ov_mod, ov_add, ov_omit],
    )

    assert (
        effective.statistics.total_courses == 3
    )  # COS101, COS102, GNS101 (CSC201 omitted)
    assert effective.statistics.total_credit_units == 2 + 3 + 2  # 7
    assert effective.statistics.national_courses_count == 1  # COS101
    assert effective.statistics.modified_courses_count == 1  # COS102
    assert effective.statistics.custom_courses_count == 1  # GNS101
    assert effective.statistics.omitted_courses_count == 1  # CSC201

    assert len(effective.omitted_courses) == 1
    assert effective.omitted_courses[0].code == "CSC201"
    assert effective.omitted_courses[0].reason == "Omitted in favor of faculty elective"

    # Verify COS102 has modified origin and applied override provenance
    cos102 = [c for c in effective.courses if c.code == "COS102"][0]
    assert cos102.credit_units == 3
    assert cos102.origin == EntityOrigin.INSTITUTIONAL_MODIFIED
    assert len(cos102.applied_overrides) == 1
    assert (
        cos102.applied_overrides[0].reason
        == "Senate approved 3 units for laboratory component"
    )

    # Verify GNS101 has custom origin and structured topic/outcomes
    gns101 = [c for c in effective.courses if c.code == "GNS101"][0]
    assert gns101.origin == EntityOrigin.INSTITUTIONAL_CUSTOM
    assert len(gns101.topics) == 1
    assert gns101.topics[0].title == "Grammar"
    assert len(gns101.topics[0].outcomes) == 1


def test_effective_curriculum_resolver_pinning_verification_failures() -> None:
    benchmark, courses = _sample_benchmark()
    resolver = EffectiveCurriculumResolver()

    # Mismatched benchmark curriculum ID
    bad_id_adoption = InstitutionalAdoption.create_draft(
        tenant_id="futa",
        programme_id="csc",
        benchmark_curriculum_id="wrong-id",
        benchmark_version=benchmark.version,
        benchmark_fingerprint=benchmark.review_fingerprint,
        adopted_by="admin-1",
        adopted_by_email="dean@futa.edu.ng",
    )
    with pytest.raises(ValueError, match="does not match loaded benchmark ID"):
        resolver.resolve(bad_id_adoption, benchmark, courses, [])

    # Mismatched benchmark version
    bad_ver_adoption = InstitutionalAdoption.create_draft(
        tenant_id="futa",
        programme_id="csc",
        benchmark_curriculum_id=benchmark.id,
        benchmark_version="1999.01",
        benchmark_fingerprint=benchmark.review_fingerprint,
        adopted_by="admin-1",
        adopted_by_email="dean@futa.edu.ng",
    )
    with pytest.raises(ValueError, match="does not match loaded benchmark version"):
        resolver.resolve(bad_ver_adoption, benchmark, courses, [])

    # Mismatched benchmark fingerprint
    bad_fp_adoption = InstitutionalAdoption.create_draft(
        tenant_id="futa",
        programme_id="csc",
        benchmark_curriculum_id=benchmark.id,
        benchmark_version=benchmark.version,
        benchmark_fingerprint="0" * 64,
        adopted_by="admin-1",
        adopted_by_email="dean@futa.edu.ng",
    )
    with pytest.raises(
        ValueError, match="does not match loaded benchmark review fingerprint"
    ):
        resolver.resolve(bad_fp_adoption, benchmark, courses, [])


def test_effective_curriculum_resolver_conflict_detection() -> None:
    benchmark, courses = _sample_benchmark()
    adoption = InstitutionalAdoption.create_draft(
        tenant_id="futa",
        programme_id="csc",
        benchmark_curriculum_id=benchmark.id,
        benchmark_version=benchmark.version,
        benchmark_fingerprint=benchmark.review_fingerprint,
        adopted_by="admin-1",
        adopted_by_email="dean@futa.edu.ng",
    )
    resolver = EffectiveCurriculumResolver()

    # Conflicting MODIFY and OMIT on same course
    ov_mod = CurriculumOverride.create(
        adoption_id=adoption.id,
        override_type=OverrideType.MODIFY_COURSE,
        target_course_code="COS102",
        reason="Modify units",
        created_by="admin-1",
        created_by_email="dean@futa.edu.ng",
        field_overrides={"credit_units": 3},
    )
    ov_omit = CurriculumOverride.create(
        adoption_id=adoption.id,
        override_type=OverrideType.OMIT_COURSE,
        target_course_code="COS102",
        reason="Omit course",
        created_by="admin-1",
        created_by_email="dean@futa.edu.ng",
    )

    with pytest.raises(
        ValueError,
        match="conflicting overrides for course 'COS102': cannot modify and omit the same course",
    ):
        resolver.resolve(adoption, benchmark, courses, [ov_mod, ov_omit])

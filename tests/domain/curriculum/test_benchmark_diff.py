from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)
from app.domain.curriculum.diff import (
    BenchmarkCurriculumDiffEngine,
    DiffAction,
)


def _create_sample_tree_v1() -> tuple[BenchmarkCurriculum, list[BenchmarkCourse]]:
    c = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-1",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
    )
    c1 = BenchmarkCourse.create(
        benchmark_curriculum_id=c.id,
        code="CSC101",
        title="Intro to CS",
        credit_units=3,
        level=100,
        semester=1,
        sequence=1,
    )
    t1 = BenchmarkTopic.create(
        benchmark_course_id=c1.id,
        sequence=1,
        title="Hardware",
    )
    o1 = BenchmarkOutcome.create(
        benchmark_topic_id=t1.id,
        sequence=1,
        description="Explain CPU architecture.",
        bloom_level=BloomTaxonomyLevel.UNDERSTAND,
    )
    t1.add_outcome(o1)
    c1.add_topic(t1)

    c2 = BenchmarkCourse.create(
        benchmark_curriculum_id=c.id,
        code="CSC102",
        title="Programming in C",
        credit_units=2,
        level=100,
        semester=2,
        sequence=2,
    )
    return c, [c1, c2]


def test_diff_identical_trees_produces_no_changes() -> None:
    curr1, courses1 = _create_sample_tree_v1()
    curr2, courses2 = _create_sample_tree_v1()
    curr2.version = "2026.02"

    engine = BenchmarkCurriculumDiffEngine()
    diff = engine.compare(curr1, courses1, curr2, courses2)

    assert diff.source_version == "2026.01"
    assert diff.target_version == "2026.02"
    assert len(diff.course_diffs) == 0
    assert diff.statistics.courses_added == 0
    assert diff.statistics.courses_removed == 0
    assert diff.statistics.courses_modified == 0
    assert diff.statistics.credit_units_delta == 0
    assert len(diff.diff_fingerprint) == 64


def test_diff_course_addition_removal_and_credit_mutation() -> None:
    curr1, courses1 = _create_sample_tree_v1()

    # V2 changes:
    # CSC101 -> REMOVED
    # CSC102 -> MODIFIED (2 credits -> 3 credits)
    # CSC103 -> ADDED (3 credits)
    curr2 = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-2",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.02",
    )
    c2_mod = BenchmarkCourse.create(
        benchmark_curriculum_id=curr2.id,
        code="CSC102",
        title="Programming in C",
        credit_units=3,  # Changed from 2 to 3
        level=100,
        semester=2,
        sequence=1,
    )
    c3_new = BenchmarkCourse.create(
        benchmark_curriculum_id=curr2.id,
        code="CSC103",
        title="Discrete Mathematics",
        credit_units=3,
        level=100,
        semester=1,
        sequence=2,
    )

    engine = BenchmarkCurriculumDiffEngine()
    diff = engine.compare(curr1, courses1, curr2, [c2_mod, c3_new])

    assert diff.statistics.courses_added == 1
    assert diff.statistics.courses_removed == 1
    assert diff.statistics.courses_modified == 1
    # Before: 3 (CSC101) + 2 (CSC102) = 5. After: 3 (CSC102) + 3 (CSC103) = 6. Delta: +1
    assert diff.statistics.credit_units_before == 5
    assert diff.statistics.credit_units_after == 6
    assert diff.statistics.credit_units_delta == 1

    diff_map = {d.code: d for d in diff.course_diffs}
    assert diff_map["CSC101"].action == DiffAction.REMOVED
    assert diff_map["CSC103"].action == DiffAction.ADDED
    assert diff_map["CSC102"].action == DiffAction.MODIFIED

    # Check field diffs for CSC102
    field_diffs = {f.field: f for f in diff_map["CSC102"].field_diffs}
    assert field_diffs["credit_units"].old_value == 2
    assert field_diffs["credit_units"].new_value == 3
    assert field_diffs["sequence"].old_value == 2
    assert field_diffs["sequence"].new_value == 1


def test_diff_topic_and_outcome_mutations() -> None:
    curr1, courses1 = _create_sample_tree_v1()

    # In V2, CSC101 topic 1 title changes and outcome 1 Bloom level changes
    curr2, courses2 = _create_sample_tree_v1()
    courses2[0].topics[0].title = "Modern CPU Architecture"
    courses2[0].topics[0].outcomes[0].bloom_level = BloomTaxonomyLevel.ANALYZE

    engine = BenchmarkCurriculumDiffEngine()
    diff = engine.compare(curr1, courses1, curr2, courses2)

    assert diff.statistics.courses_modified == 1
    assert diff.statistics.topics_modified == 1
    assert diff.statistics.outcomes_modified == 1

    c1_diff = diff.course_diffs[0]
    assert c1_diff.code == "CSC101"
    assert c1_diff.action == DiffAction.MODIFIED
    assert len(c1_diff.topic_diffs) == 1

    t_diff = c1_diff.topic_diffs[0]
    assert t_diff.action == DiffAction.MODIFIED
    t_field_map = {f.field: f for f in t_diff.field_diffs}
    assert t_field_map["title"].old_value == "Hardware"
    assert t_field_map["title"].new_value == "Modern CPU Architecture"

    assert len(t_diff.outcome_diffs) == 1
    o_diff = t_diff.outcome_diffs[0]
    assert o_diff.action == DiffAction.MODIFIED
    o_field_map = {f.field: f for f in o_diff.field_diffs}
    assert o_field_map["bloom_level"].old_value == "understand"
    assert o_field_map["bloom_level"].new_value == "analyze"

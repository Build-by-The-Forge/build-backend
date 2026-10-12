from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkStatus,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)
from app.domain.curriculum.validator import (
    BenchmarkCurriculumValidator,
    IssueSeverity,
)


def _build_valid_tree() -> tuple[BenchmarkCurriculum, list[BenchmarkCourse]]:
    curriculum = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-1",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="CSC",
        version="2026.01",
        minimum_credit_units=6,
    )
    c1 = BenchmarkCourse.create(
        benchmark_curriculum_id=curriculum.id,
        code="COS101",
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
        benchmark_curriculum_id=curriculum.id,
        code="COS102",
        title="Programming in C",
        credit_units=3,
        level=100,
        semester=2,
        sequence=2,
    )
    t2 = BenchmarkTopic.create(
        benchmark_course_id=c2.id,
        sequence=1,
        title="Pointers",
    )
    o2 = BenchmarkOutcome.create(
        benchmark_topic_id=t2.id,
        sequence=1,
        description="Apply pointer arithmetic in memory buffers.",
        bloom_level=BloomTaxonomyLevel.APPLY,
    )
    t2.add_outcome(o2)
    c2.add_topic(t2)

    return curriculum, [c1, c2]


def test_validator_passes_valid_curriculum_tree() -> None:
    curriculum, courses = _build_valid_tree()
    validator = BenchmarkCurriculumValidator()

    result = validator.validate(curriculum, courses)
    assert result.is_valid is True
    assert result.error_count == 0
    assert result.warning_count == 0
    assert len(result.issues) == 0

    curriculum.mark_validated()
    assert curriculum.status == BenchmarkStatus.VALIDATED
    events = curriculum.pull_events()
    assert len(events) == 2  # candidate_created + benchmark_validated
    assert events[1].event_type == "curriculum.benchmark_validated"


def test_validator_flags_empty_courses() -> None:
    curriculum, _ = _build_valid_tree()
    validator = BenchmarkCurriculumValidator()

    result = validator.validate(curriculum, [])
    assert result.is_valid is False
    assert result.error_count == 1
    assert any(i.rule == "NON_EMPTY_COURSES" for i in result.issues)


def test_validator_flags_course_without_topics() -> None:
    curriculum, courses = _build_valid_tree()
    # Remove topics from course 1
    courses[0].topics = []

    validator = BenchmarkCurriculumValidator()
    result = validator.validate(curriculum, courses)

    assert result.is_valid is False
    assert result.error_count == 1
    assert any(i.rule == "NON_EMPTY_TOPICS" and i.entity_identifier == "COS101" for i in result.issues)


def test_validator_flags_non_monotonic_topic_sequences() -> None:
    curriculum, courses = _build_valid_tree()
    # Add a topic with sequence 3 instead of sequential 2
    gap_topic = BenchmarkTopic(
        id="top-gap",
        benchmark_course_id=courses[0].id,
        sequence=3,
        title="Operating Systems",
        outcomes=[
            BenchmarkOutcome.create(
                benchmark_topic_id="top-gap",
                sequence=1,
                description="Describe processes.",
            )
        ],
    )
    courses[0].topics.append(gap_topic)

    validator = BenchmarkCurriculumValidator()
    result = validator.validate(curriculum, courses)

    assert result.is_valid is False
    assert result.error_count == 1
    assert any(i.rule == "MONOTONIC_SEQUENCE" for i in result.issues)


def test_validator_flags_topic_without_outcomes() -> None:
    curriculum, courses = _build_valid_tree()
    courses[0].topics[0].outcomes = []

    validator = BenchmarkCurriculumValidator()
    result = validator.validate(curriculum, courses)

    assert result.is_valid is False
    assert result.error_count == 1
    assert any(i.rule == "NON_EMPTY_OUTCOMES" for i in result.issues)


def test_validator_flags_short_outcome_description() -> None:
    curriculum, courses = _build_valid_tree()
    courses[0].topics[0].outcomes[0].description = "Bad"

    validator = BenchmarkCurriculumValidator()
    result = validator.validate(curriculum, courses)

    assert result.is_valid is False
    assert result.error_count == 1
    assert any(i.rule == "DESCRIPTION_LENGTH" for i in result.issues)


def test_validator_flags_minimum_credit_warning() -> None:
    curriculum, courses = _build_valid_tree()
    # Require 120 credits when only 6 are present
    curriculum.minimum_credit_units = 120

    validator = BenchmarkCurriculumValidator()
    result = validator.validate(curriculum, courses)

    # Warnings do not invalidate candidate
    assert result.is_valid is True
    assert result.error_count == 0
    assert result.warning_count == 1
    assert result.issues[0].severity == IssueSeverity.WARNING
    assert result.issues[0].rule == "MINIMUM_CREDIT_UNITS"

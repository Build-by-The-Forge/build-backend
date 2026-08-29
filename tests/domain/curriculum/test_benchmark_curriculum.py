import pytest
from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkStatus,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)


def test_create_benchmark_candidate_success() -> None:
    curriculum = BenchmarkCurriculum.create_candidate(
        source_snapshot_id="snap-123",
        discipline_group="Computing",
        programme_name="Computer Science",
        programme_code="csc",
        version="2026.01",
        minimum_credit_units=120,
    )

    assert curriculum.id.startswith("bmcurr-")
    assert curriculum.source_snapshot_id == "snap-123"
    assert curriculum.discipline_group == "Computing"
    assert curriculum.programme_name == "Computer Science"
    assert curriculum.programme_code == "CSC"
    assert curriculum.version == "2026.01"
    assert curriculum.status == BenchmarkStatus.CANDIDATE
    assert curriculum.is_mutable() is True

    events = curriculum.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "curriculum.benchmark_candidate_created"
    assert events[0].payload["programme_code"] == "CSC"


def test_create_benchmark_candidate_validation_errors() -> None:
    with pytest.raises(ValueError, match="source_snapshot_id cannot be empty"):
        BenchmarkCurriculum.create_candidate(
            source_snapshot_id="  ",
            discipline_group="Computing",
            programme_name="Computer Science",
            programme_code="CSC",
            version="2026.01",
        )

    with pytest.raises(ValueError, match="programme_code cannot be empty"):
        BenchmarkCurriculum.create_candidate(
            source_snapshot_id="snap-123",
            discipline_group="Computing",
            programme_name="Computer Science",
            programme_code="   ",
            version="2026.01",
        )


def test_create_benchmark_course_topic_outcome_hierarchy() -> None:
    course = BenchmarkCourse.create(
        benchmark_curriculum_id="bmcurr-1",
        code="cos 102",
        title="Introduction to Programming",
        credit_units=3,
        level=100,
        semester=2,
        is_compulsory=True,
        course_category="core",
        description="Foundational programming in C.",
        sequence=1,
    )
    assert course.code == "COS102"
    assert course.credit_units == 3
    assert course.level == 100
    assert course.semester == 2
    assert course.course_category == "core"

    topic1 = BenchmarkTopic.create(
        benchmark_course_id=course.id,
        sequence=1,
        title="Memory Management & Pointers",
        description="Stack, heap, pointer arithmetic",
    )
    assert topic1.sequence == 1
    assert topic1.title == "Memory Management & Pointers"

    outcome1 = BenchmarkOutcome.create(
        benchmark_topic_id=topic1.id,
        sequence=1,
        description="Allocate dynamic memory in C safely.",
        bloom_level=BloomTaxonomyLevel.APPLY,
    )
    assert outcome1.sequence == 1
    assert outcome1.bloom_level == BloomTaxonomyLevel.APPLY

    topic1.add_outcome(outcome1)
    assert len(topic1.outcomes) == 1

    # Duplicate sequence in topic raises
    with pytest.raises(ValueError, match="already exists in topic"):
        topic1.add_outcome(
            BenchmarkOutcome.create(
                benchmark_topic_id=topic1.id,
                sequence=1,
                description="Duplicate sequence outcome",
            )
        )

    course.add_topic(topic1)
    assert len(course.topics) == 1

    # Duplicate topic sequence in course raises
    with pytest.raises(ValueError, match="already exists in course"):
        course.add_topic(
            BenchmarkTopic.create(
                benchmark_course_id=course.id,
                sequence=1,
                title="Duplicate Topic Sequence",
            )
        )


def test_benchmark_course_invalid_fields() -> None:
    with pytest.raises(ValueError, match="credit_units must be between 1 and 12"):
        BenchmarkCourse.create(
            benchmark_curriculum_id="bmcurr-1",
            code="CSC101",
            title="Title",
            credit_units=0,
            level=100,
            semester=1,
        )

    with pytest.raises(ValueError, match="level must be one of"):
        BenchmarkCourse.create(
            benchmark_curriculum_id="bmcurr-1",
            code="CSC101",
            title="Title",
            credit_units=3,
            level=150,
            semester=1,
        )

    with pytest.raises(ValueError, match="semester must be 1 or 2"):
        BenchmarkCourse.create(
            benchmark_curriculum_id="bmcurr-1",
            code="CSC101",
            title="Title",
            credit_units=3,
            level=100,
            semester=3,
        )

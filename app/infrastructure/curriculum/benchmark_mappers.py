from __future__ import annotations

from app.domain.curriculum.benchmark import (
    BenchmarkCourse,
    BenchmarkCurriculum,
    BenchmarkOutcome,
    BenchmarkStatus,
    BenchmarkTopic,
    BloomTaxonomyLevel,
)
from app.infrastructure.db.models.benchmark import (
    BenchmarkCourseModel,
    BenchmarkCurriculumModel,
    BenchmarkLearningOutcomeModel,
    BenchmarkTopicModel,
)


def benchmark_curriculum_to_model(
    curriculum: BenchmarkCurriculum,
    model: BenchmarkCurriculumModel | None = None,
) -> BenchmarkCurriculumModel:
    if model is None:
        return BenchmarkCurriculumModel(
            id=curriculum.id,
            source_snapshot_id=curriculum.source_snapshot_id,
            discipline_group=curriculum.discipline_group,
            programme_name=curriculum.programme_name,
            programme_code=curriculum.programme_code,
            degree_level=curriculum.degree_level,
            version=curriculum.version,
            minimum_credit_units=curriculum.minimum_credit_units,
            status=curriculum.status.value,
            created_at=curriculum.created_at,
            updated_at=curriculum.updated_at,
        )
    model.discipline_group = curriculum.discipline_group
    model.programme_name = curriculum.programme_name
    model.programme_code = curriculum.programme_code
    model.degree_level = curriculum.degree_level
    model.version = curriculum.version
    model.minimum_credit_units = curriculum.minimum_credit_units
    model.status = curriculum.status.value
    model.updated_at = curriculum.updated_at
    return model


def benchmark_curriculum_model_to_domain(
    model: BenchmarkCurriculumModel,
) -> BenchmarkCurriculum:
    return BenchmarkCurriculum(
        id=model.id,
        source_snapshot_id=model.source_snapshot_id,
        discipline_group=model.discipline_group,
        programme_name=model.programme_name,
        programme_code=model.programme_code,
        degree_level=model.degree_level,
        version=model.version,
        minimum_credit_units=model.minimum_credit_units,
        status=BenchmarkStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def benchmark_course_to_model(
    course: BenchmarkCourse, model: BenchmarkCourseModel | None = None
) -> BenchmarkCourseModel:
    if model is None:
        m = BenchmarkCourseModel(
            id=course.id,
            benchmark_curriculum_id=course.benchmark_curriculum_id,
            code=course.code,
            title=course.title,
            credit_units=course.credit_units,
            level=course.level,
            semester=course.semester,
            is_compulsory=course.is_compulsory,
            course_category=course.course_category,
            description=course.description,
            sequence=course.sequence,
            created_at=course.created_at,
        )
        for topic in course.topics:
            m.topics.append(benchmark_topic_to_model(topic))
        return m

    model.code = course.code
    model.title = course.title
    model.credit_units = course.credit_units
    model.level = course.level
    model.semester = course.semester
    model.is_compulsory = course.is_compulsory
    model.course_category = course.course_category
    model.description = course.description
    model.sequence = course.sequence
    return model


def benchmark_course_model_to_domain(
    model: BenchmarkCourseModel, include_topics: bool = True
) -> BenchmarkCourse:
    topics = []
    if include_topics and model.topics:
        topics = [benchmark_topic_model_to_domain(t) for t in model.topics]

    return BenchmarkCourse(
        id=model.id,
        benchmark_curriculum_id=model.benchmark_curriculum_id,
        code=model.code,
        title=model.title,
        credit_units=model.credit_units,
        level=model.level,
        semester=model.semester,
        is_compulsory=model.is_compulsory,
        course_category=model.course_category,
        description=model.description,
        sequence=model.sequence,
        topics=topics,
        created_at=model.created_at,
    )


def benchmark_topic_to_model(
    topic: BenchmarkTopic, model: BenchmarkTopicModel | None = None
) -> BenchmarkTopicModel:
    if model is None:
        m = BenchmarkTopicModel(
            id=topic.id,
            benchmark_course_id=topic.benchmark_course_id,
            sequence=topic.sequence,
            title=topic.title,
            description=topic.description,
            created_at=topic.created_at,
        )
        for outcome in topic.outcomes:
            m.outcomes.append(benchmark_outcome_to_model(outcome))
        return m

    model.sequence = topic.sequence
    model.title = topic.title
    model.description = topic.description
    return model


def benchmark_topic_model_to_domain(
    model: BenchmarkTopicModel,
) -> BenchmarkTopic:
    outcomes = []
    if model.outcomes:
        outcomes = [benchmark_outcome_model_to_domain(o) for o in model.outcomes]

    return BenchmarkTopic(
        id=model.id,
        benchmark_course_id=model.benchmark_course_id,
        sequence=model.sequence,
        title=model.title,
        description=model.description,
        outcomes=outcomes,
        created_at=model.created_at,
    )


def benchmark_outcome_to_model(
    outcome: BenchmarkOutcome,
    model: BenchmarkLearningOutcomeModel | None = None,
) -> BenchmarkLearningOutcomeModel:
    if model is None:
        return BenchmarkLearningOutcomeModel(
            id=outcome.id,
            benchmark_topic_id=outcome.benchmark_topic_id,
            sequence=outcome.sequence,
            description=outcome.description,
            bloom_taxonomy_level=(
                outcome.bloom_level.value if outcome.bloom_level else None
            ),
            created_at=outcome.created_at,
        )

    model.sequence = outcome.sequence
    model.description = outcome.description
    model.bloom_taxonomy_level = (
        outcome.bloom_level.value if outcome.bloom_level else None
    )
    return model


def benchmark_outcome_model_to_domain(
    model: BenchmarkLearningOutcomeModel,
) -> BenchmarkOutcome:
    bloom_level = None
    if model.bloom_taxonomy_level:
        bloom_level = BloomTaxonomyLevel(model.bloom_taxonomy_level)

    return BenchmarkOutcome(
        id=model.id,
        benchmark_topic_id=model.benchmark_topic_id,
        sequence=model.sequence,
        description=model.description,
        bloom_level=bloom_level,
        created_at=model.created_at,
    )

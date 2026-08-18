from __future__ import annotations

from app.domain.catalogue.course import Course
from app.domain.catalogue.learning_outcome import LearningOutcome
from app.domain.catalogue.reference_material import ReferenceMaterial
from app.domain.catalogue.topic import Topic
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseId,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseStatus,
    CourseTitle,
    DepartmentId,
    LearningOutcomeDescription,
    LearningOutcomeId,
    LearningOutcomeSequence,
    LearningOutcomeStatus,
    ReferenceMaterialId,
    ReferenceMaterialStatus,
    ReferenceMaterialTitle,
    ReferenceMaterialType,
    ReferenceMaterialUrl,
    TopicDescription,
    TopicId,
    TopicLevel,
    TopicSequence,
    TopicSlug,
    TopicStatus,
    TopicTitle,
)
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    LearningOutcomeModel,
    ReferenceMaterialModel,
    TopicModel,
)


def learning_outcome_to_model(
    learning_outcome: LearningOutcome,
    model: LearningOutcomeModel | None = None,
) -> LearningOutcomeModel:
    if model is None:
        model = LearningOutcomeModel(id=learning_outcome.id.value)

    model.topic_id = learning_outcome.topic_id.value
    model.sequence = int(learning_outcome.sequence.value)
    model.description = learning_outcome.description.value
    model.status = learning_outcome.status.value
    model.created_at = learning_outcome.created_at
    model.updated_at = learning_outcome.updated_at
    return model


def topic_to_model(topic: Topic, model: TopicModel | None = None) -> TopicModel:
    if model is None:
        model = TopicModel(id=topic.id.value)

    model.course_id = topic.course_id.value
    model.sequence = int(topic.sequence.value)
    model.title = topic.title.value
    model.slug = topic.slug.value
    model.description = topic.description.value if topic.description is not None else None
    model.level = topic.level.value
    model.status = topic.status.value
    model.created_at = topic.created_at
    model.updated_at = topic.updated_at

    existing_outcomes = {outcome.id: outcome for outcome in model.learning_outcomes or []}
    model.learning_outcomes = [
        learning_outcome_to_model(
            outcome,
            model=existing_outcomes.get(outcome.id.value),
        )
        for outcome in topic.learning_outcomes
    ]
    return model


def reference_material_to_model(
    reference: ReferenceMaterial,
    model: ReferenceMaterialModel | None = None,
) -> ReferenceMaterialModel:
    if model is None:
        model = ReferenceMaterialModel(id=reference.id.value)

    model.course_id = reference.course_id.value
    model.title = reference.title.value
    model.material_type = reference.material_type.value
    model.url = reference.url.value if reference.url is not None else None
    model.status = reference.status.value
    model.created_at = reference.created_at
    model.updated_at = reference.updated_at
    return model


def course_to_model(course: Course, model: CourseModel | None = None) -> CourseModel:
    if model is None:
        model = CourseModel(id=course.id.value)

    model.department_id = course.department_id.value
    model.code = course.code.value
    model.title = course.title.value
    model.slug = course.slug.value
    model.credit_units = course.credit_units.value
    model.level = course.level.value
    model.semester = course.semester.value
    model.status = course.status.value
    model.description = course.description
    model.created_at = course.created_at
    model.updated_at = course.updated_at

    existing_topics = {topic.id: topic for topic in model.topics or []}
    model.topics = [
        topic_to_model(topic, model=existing_topics.get(topic.id.value))
        for topic in course.topics
    ]

    existing_refs = {ref.id: ref for ref in model.reference_materials or []}
    model.reference_materials = [
        reference_material_to_model(
            reference,
            model=existing_refs.get(reference.id.value),
        )
        for reference in course.references
    ]
    return model


def learning_outcome_model_to_domain(model: LearningOutcomeModel) -> LearningOutcome:
    return LearningOutcome(
        id=LearningOutcomeId(model.id),
        topic_id=TopicId(model.topic_id),
        sequence=LearningOutcomeSequence(model.sequence),
        description=LearningOutcomeDescription(model.description),
        status=LearningOutcomeStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def topic_model_to_domain(model: TopicModel) -> Topic:
    return Topic(
        id=TopicId(model.id),
        course_id=CourseId(model.course_id),
        sequence=TopicSequence(model.sequence),
        title=TopicTitle(model.title),
        slug=TopicSlug(model.slug),
        description=TopicDescription(model.description) if model.description is not None else None,
        level=TopicLevel(model.level),
        status=TopicStatus(model.status),
        learning_outcomes=[learning_outcome_model_to_domain(lo) for lo in model.learning_outcomes],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def reference_material_model_to_domain(model: ReferenceMaterialModel) -> ReferenceMaterial:
    return ReferenceMaterial(
        id=ReferenceMaterialId(model.id),
        course_id=CourseId(model.course_id),
        title=ReferenceMaterialTitle(model.title),
        material_type=ReferenceMaterialType(model.material_type),
        url=ReferenceMaterialUrl(model.url) if model.url is not None else None,
        status=ReferenceMaterialStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def course_to_domain(model: CourseModel) -> Course:
    return Course(
        id=CourseId(model.id),
        department_id=DepartmentId(model.department_id),
        code=CourseCode(model.code),
        title=CourseTitle(model.title),
        slug=CourseSlug(model.slug),
        credit_units=CourseCreditUnits(model.credit_units),
        level=CourseLevel(model.level),
        semester=CourseSemester(model.semester),
        status=CourseStatus(model.status),
        description=model.description,
        topics=[topic_model_to_domain(topic) for topic in model.topics],
        references=[reference_material_model_to_domain(ref) for ref in model.reference_materials],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )

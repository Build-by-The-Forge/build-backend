import uuid
from datetime import datetime, timezone

import pytest

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
    CourseTitle,
    DepartmentId,
    LearningOutcomeDescription,
    LearningOutcomeSequence,
    ReferenceMaterialTitle,
    ReferenceMaterialType,
    ReferenceMaterialUrl,
    TopicDescription,
    TopicId,
    TopicLevel,
    TopicSequence,
    TopicSlug,
    TopicTitle,
)
from app.infrastructure.catalogue.repositories import SqlAlchemyCourseRepository
from app.infrastructure.db.models.tenant_core import (
    TenantModel,
    FacultyModel,
    DepartmentModel,
)


@pytest.mark.asyncio
async def test_course_repository_save_get_list(session):
    tenant_id = str(uuid.uuid4())
    faculty_id = str(uuid.uuid4())
    department_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)

    tenant = TenantModel(
        id=tenant_id,
        name="T",
        slug="t",
        created_at=now,
        updated_at=now,
        status="active",
    )
    faculty = FacultyModel(
        id=faculty_id,
        tenant_id=tenant_id,
        name="F",
        slug="f",
        created_at=now,
        updated_at=now,
        status="active",
    )
    department = DepartmentModel(
        id=department_id,
        tenant_id=tenant_id,
        faculty_id=faculty_id,
        name="D",
        slug="d",
        code="DPT",
        created_at=now,
        updated_at=now,
        status="active",
    )

    session.add_all([tenant, faculty, department])
    await session.flush()

    repo = SqlAlchemyCourseRepository(session)

    course = Course.create(
        department_id=DepartmentId(department_id),
        code=CourseCode("CS101"),
        title=CourseTitle("Intro to CS"),
        slug=CourseSlug("intro-to-cs"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )

    topic = Topic.create(
        course_id=course.id,
        title=TopicTitle("Intro Topic"),
        slug=TopicSlug("intro-topic"),
        description=TopicDescription("A starting topic."),
        level=TopicLevel.PRIMARY,
        sequence=TopicSequence(1),
    )
    outcome = LearningOutcome.create(
        topic_id=topic.id,
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Describe the course overview."),
    )
    topic.add_learning_outcome(outcome)
    course.add_topic(topic)

    reference = ReferenceMaterial.create(
        course_id=course.id,
        title=ReferenceMaterialTitle("Course Handbook"),
        material_type=ReferenceMaterialType.LINK,
        url=ReferenceMaterialUrl("https://example.com/handbook"),
    )
    course.add_reference(reference)

    await repo.save(course, tenant_id=tenant_id)

    fetched = await repo.get_by_id(course.id.value, tenant_id=tenant_id)
    assert fetched is not None
    assert fetched.code.value == course.code.value
    assert len(fetched.topics) == 1
    assert fetched.topics[0].sequence.value == 1
    assert len(fetched.topics[0].learning_outcomes) == 1
    assert fetched.references[0].title.value == reference.title.value

    all_courses = await repo.list_all(tenant_id=tenant_id)
    assert any(c.id.value == course.id.value for c in all_courses)

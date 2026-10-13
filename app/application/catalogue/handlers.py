from app.application.catalogue.commands import (
    CreateCourseCommand,
    CreateLearningOutcomeCommand,
    CreateReferenceMaterialCommand,
    CreateTopicCommand,
    UpdateCourseCommand,
    UpdateLearningOutcomeCommand,
    UpdateReferenceMaterialCommand,
    UpdateTopicCommand,
)
from app.domain.catalogue.course import Course
from app.domain.catalogue.learning_outcome import LearningOutcome
from app.domain.catalogue.reference_material import ReferenceMaterial
from app.domain.catalogue.topic import Topic
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
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
    TopicSequence,
    TopicSlug,
    TopicTitle,
)
from app.domain.repositories.course import CourseRepository


class CreateCourseHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateCourseCommand) -> Course:
        course = Course.create(
            department_id=DepartmentId(command.department_id),
            code=CourseCode(command.code),
            title=CourseTitle(command.title),
            slug=CourseSlug(command.slug),
            credit_units=CourseCreditUnits(command.credit_units),
            level=CourseLevel(command.level),
            semester=CourseSemester(command.semester),
            description=command.description,
        )
        return await self.repository.save(course, tenant_id=command.tenant_id)


class ListCoursesHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, department_id: str | None = None, tenant_id: str | None = None) -> list[Course]:
        if department_id:
            return await self.repository.list_by_department(department_id, tenant_id=tenant_id)
        return await self.repository.list_all(tenant_id=tenant_id)


class CreateTopicHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateTopicCommand) -> Topic | None:
        course = await self.repository.get_by_id(command.course_id, tenant_id=command.tenant_id)
        if course is None:
            return None

        topic = Topic.create(
            course_id=course.id,
            title=TopicTitle(command.title),
            slug=TopicSlug(command.slug),
            description=(TopicDescription(command.description) if command.description is not None else None),
            sequence=TopicSequence(command.sequence),
        )
        course.add_topic(topic)
        await self.repository.save(course, tenant_id=command.tenant_id)
        return topic


class UpdateTopicHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateTopicCommand) -> Topic | None:
        course = await self.repository.get_by_topic_id(command.topic_id, tenant_id=command.tenant_id)
        if course is None:
            return None
        topic = next(
            (candidate for candidate in course.topics if candidate.id.value == command.topic_id),
            None,
        )
        if topic is None:
            return None
        topic.update_details(
            title=TopicTitle(command.title) if command.title is not None else None,
            description=(TopicDescription(command.description) if command.description is not None else None),
        )
        await self.repository.save(course, tenant_id=command.tenant_id)
        return topic


class CreateLearningOutcomeHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateLearningOutcomeCommand) -> LearningOutcome | None:
        course = await self.repository.get_by_topic_id(command.topic_id, tenant_id=command.tenant_id)
        if course is None:
            return None
        topic = next(
            (item for item in course.topics if item.id.value == command.topic_id),
            None,
        )
        if topic is None:
            return None
        outcome = LearningOutcome.create(
            topic_id=topic.id,
            sequence=LearningOutcomeSequence(command.sequence),
            description=LearningOutcomeDescription(command.description),
        )
        topic.add_learning_outcome(outcome)
        await self.repository.save(course, tenant_id=command.tenant_id)
        return outcome


class UpdateLearningOutcomeHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateLearningOutcomeCommand) -> LearningOutcome | None:
        course = await self.repository.get_by_learning_outcome_id(command.learning_outcome_id, tenant_id=command.tenant_id)
        if course is None:
            return None
        outcome = next(
            (item for topic in course.topics for item in topic.learning_outcomes if item.id.value == command.learning_outcome_id),
            None,
        )
        if outcome is None:
            return None
        if command.description is not None:
            outcome.update_description(LearningOutcomeDescription(command.description))
        await self.repository.save(course, tenant_id=command.tenant_id)
        return outcome


class CreateReferenceMaterialHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: CreateReferenceMaterialCommand) -> ReferenceMaterial | None:
        course = await self.repository.get_by_topic_id(command.topic_id, tenant_id=command.tenant_id)
        if course is None:
            return None
        if not any(topic.id.value == command.topic_id for topic in course.topics):
            return None
        material = ReferenceMaterial.create(
            course_id=course.id,
            title=ReferenceMaterialTitle(command.title),
            material_type=ReferenceMaterialType(command.material_type),
            url=(ReferenceMaterialUrl(command.url) if command.url is not None else None),
        )
        course.add_reference(material)
        await self.repository.save(course, tenant_id=command.tenant_id)
        return material


class UpdateReferenceMaterialHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateReferenceMaterialCommand) -> ReferenceMaterial | None:
        course = await self.repository.get_by_reference_material_id(command.reference_material_id, tenant_id=command.tenant_id)
        if course is None:
            return None
        material = next(
            (item for item in course.references if item.id.value == command.reference_material_id),
            None,
        )
        if material is None:
            return None
        material.update_details(
            title=(ReferenceMaterialTitle(command.title) if command.title is not None else None),
            material_type=(ReferenceMaterialType(command.material_type) if command.material_type is not None else None),
            url=(ReferenceMaterialUrl(command.url) if command.url is not None else None),
        )
        await self.repository.save(course, tenant_id=command.tenant_id)
        return material


class UpdateCourseHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, command: UpdateCourseCommand) -> Course | None:
        course = await self.repository.get_by_id(command.course_id, tenant_id=command.tenant_id)
        if course is None:
            return None
        course.update_details(
            title=CourseTitle(command.title) if command.title is not None else None,
            description=command.description,
        )
        return await self.repository.save(course, tenant_id=command.tenant_id)


class TransitionCourseHandler:
    def __init__(self, repository: CourseRepository) -> None:
        self.repository = repository

    async def handle(self, course_id: str, tenant_id: str | None, transition: str) -> Course | None:
        course = await self.repository.get_by_id(course_id, tenant_id=tenant_id)
        if course is None:
            return None
        if transition == "publish":
            course.publish()
        else:
            course.archive()
        return await self.repository.save(course, tenant_id=tenant_id)

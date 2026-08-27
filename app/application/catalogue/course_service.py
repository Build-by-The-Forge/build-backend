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
from app.application.catalogue.handlers import (
    CreateCourseHandler,
    CreateLearningOutcomeHandler,
    CreateReferenceMaterialHandler,
    CreateTopicHandler,
    ListCoursesHandler,
    TransitionCourseHandler,
    UpdateCourseHandler,
    UpdateLearningOutcomeHandler,
    UpdateReferenceMaterialHandler,
    UpdateTopicHandler,
)
from app.application.common.uow import CourseUnitOfWorkFactory
from app.domain.repositories.course import CourseRepository

class CourseService:
    def __init__(
        self,
        repository: CourseRepository | None = None,
        uow_factory: CourseUnitOfWorkFactory | None = None,
    ) -> None:
        self.repository = repository
        self.uow_factory = uow_factory

    async def create_course(
        self,
        department_id: str,
        code: str,
        title: str,
        slug: str,
        credit_units: int,
        level: int,
        semester: int,
        description: str | None = None,
        tenant_id: str | None = None,
    ):
        command = CreateCourseCommand(
            department_id=department_id,
            code=code,
            title=title,
            slug=slug,
            credit_units=credit_units,
            level=level,
            semester=semester,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = CreateCourseHandler(repository=uow.courses)
                return await handler.handle(command)

        handler = CreateCourseHandler(repository=self.repository)
        return await handler.handle(command)

    async def list_courses(
        self, department_id: str | None = None, tenant_id: str | None = None
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                handler = ListCoursesHandler(repository=uow.courses)
                return await handler.handle(
                    department_id=department_id, tenant_id=tenant_id
                )

        handler = ListCoursesHandler(repository=self.repository)
        return await handler.handle(department_id=department_id, tenant_id=tenant_id)

    async def get_course(self, course_id: str, tenant_id: str | None = None):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await uow.courses.get_by_id(course_id, tenant_id=tenant_id)

        return await self.repository.get_by_id(course_id, tenant_id=tenant_id)

    async def get_course_by_topic(self, topic_id: str, tenant_id: str | None = None):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await uow.courses.get_by_topic_id(topic_id, tenant_id=tenant_id)
        return await self.repository.get_by_topic_id(topic_id, tenant_id=tenant_id)

    async def update_course(
        self,
        course_id: str,
        tenant_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ):
        command = UpdateCourseCommand(
            course_id=course_id,
            title=title,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await UpdateCourseHandler(uow.courses).handle(command)
        return await UpdateCourseHandler(self.repository).handle(command)

    async def transition_course(
        self, course_id: str, tenant_id: str | None, transition: str
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await TransitionCourseHandler(uow.courses).handle(
                    course_id, tenant_id, transition
                )
        return await TransitionCourseHandler(self.repository).handle(
            course_id, tenant_id, transition
        )

    async def create_topic(
        self,
        course_id: str,
        title: str,
        slug: str,
        description: str | None = None,
        sequence: int = 1,
        tenant_id: str | None = None,
    ):
        command = CreateTopicCommand(
            course_id=course_id,
            title=title,
            slug=slug,
            description=description,
            sequence=sequence,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await CreateTopicHandler(uow.courses).handle(command)
        return await CreateTopicHandler(self.repository).handle(command)

    async def update_topic(
        self,
        topic_id: str,
        tenant_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ):
        command = UpdateTopicCommand(
            topic_id=topic_id,
            title=title,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await UpdateTopicHandler(uow.courses).handle(command)
        return await UpdateTopicHandler(self.repository).handle(command)

    async def transition_topic(
        self, topic_id: str, tenant_id: str | None, transition: str
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                course = await uow.courses.get_by_topic_id(topic_id, tenant_id)
                if course is None:
                    return None
                topic = next(
                    (item for item in course.topics if item.id.value == topic_id), None
                )
                if topic is None:
                    return None
                if transition == "archive":
                    topic.archive()
                else:
                    topic.publish()
                await uow.courses.save(course, tenant_id=tenant_id)
                return topic
        return None

    async def create_learning_outcome(
        self,
        topic_id: str,
        sequence: int,
        description: str,
        tenant_id: str | None = None,
    ):
        command = CreateLearningOutcomeCommand(
            topic_id=topic_id,
            sequence=sequence,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await CreateLearningOutcomeHandler(uow.courses).handle(command)
        return await CreateLearningOutcomeHandler(self.repository).handle(command)

    async def update_learning_outcome(
        self,
        learning_outcome_id: str,
        description: str | None = None,
        tenant_id: str | None = None,
    ):
        command = UpdateLearningOutcomeCommand(
            learning_outcome_id=learning_outcome_id,
            description=description,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await UpdateLearningOutcomeHandler(uow.courses).handle(command)
        return await UpdateLearningOutcomeHandler(self.repository).handle(command)

    async def transition_learning_outcome(
        self, learning_outcome_id: str, tenant_id: str, transition: str
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                course = await uow.courses.get_by_learning_outcome_id(
                    learning_outcome_id, tenant_id
                )
                if course is None:
                    return None
                outcome = next(
                    (
                        item
                        for topic in course.topics
                        for item in topic.learning_outcomes
                        if item.id.value == learning_outcome_id
                    ),
                    None,
                )
                if outcome is None:
                    return None
                if transition == "archive":
                    outcome.archive()
                else:
                    outcome.publish()
                await uow.courses.save(course, tenant_id=tenant_id)
                return outcome
        return None

    async def create_reference_material(
        self,
        topic_id: str,
        title: str,
        material_type: str,
        url: str | None = None,
        tenant_id: str | None = None,
    ):
        command = CreateReferenceMaterialCommand(
            topic_id=topic_id,
            title=title,
            material_type=material_type,
            url=url,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await CreateReferenceMaterialHandler(uow.courses).handle(command)
        return await CreateReferenceMaterialHandler(self.repository).handle(command)

    async def update_reference_material(
        self,
        reference_material_id: str,
        title: str | None = None,
        material_type: str | None = None,
        url: str | None = None,
        tenant_id: str | None = None,
    ):
        command = UpdateReferenceMaterialCommand(
            reference_material_id=reference_material_id,
            title=title,
            material_type=material_type,
            url=url,
            tenant_id=tenant_id,
        )
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                return await UpdateReferenceMaterialHandler(uow.courses).handle(command)
        return await UpdateReferenceMaterialHandler(self.repository).handle(command)

    async def transition_reference_material(
        self, reference_material_id: str, tenant_id: str, transition: str
    ):
        if self.uow_factory is not None:
            async with self.uow_factory() as uow:
                course = await uow.courses.get_by_reference_material_id(
                    reference_material_id, tenant_id
                )
                if course is None:
                    return None
                material = next(
                    (
                        item
                        for item in course.references
                        if item.id.value == reference_material_id
                    ),
                    None,
                )
                if material is None:
                    return None
                if transition == "archive":
                    material.archive()
                else:
                    material.publish()
                await uow.courses.save(course, tenant_id=tenant_id)
                return material
        return None

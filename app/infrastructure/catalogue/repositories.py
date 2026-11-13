from typing import TypeVar

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.catalogue.course import Course
from app.domain.catalogue.structure import DepartmentEntry, FacultyEntry, ProgrammeEntry
from app.domain.catalogue.value_objects import CourseStatus
from app.domain.repositories.course import CourseRepository
from app.infrastructure.catalogue.mappers import course_to_domain, course_to_model
from app.infrastructure.db.models.catalogue import (
    CourseModel,
    LearningOutcomeModel,
    ReferenceMaterialModel,
    TopicModel,
)
from app.infrastructure.db.models.tenant_core import DepartmentModel, FacultyModel, ProgrammeModel

StructureModel = TypeVar("StructureModel", FacultyModel, DepartmentModel, ProgrammeModel)


def _active_faculty(tenant_id: str) -> list[ColumnElement[bool]]:
    return [FacultyModel.tenant_id == tenant_id, FacultyModel.status == "active"]


def _active_department(tenant_id: str) -> list[ColumnElement[bool]]:
    """A department under an inactive faculty is out of reach too."""
    return [
        DepartmentModel.tenant_id == tenant_id,
        DepartmentModel.status == "active",
        DepartmentModel.faculty_id.in_(select(FacultyModel.id).where(*_active_faculty(tenant_id))),
    ]


def readable_programme(tenant_id: str) -> list[ColumnElement[bool]]:
    """A programme a student can read (listProgrammes): active, under an
    active department of an active faculty, that department in the
    programme's own faculty. Correlated only to programmes, so it holds in a
    query that also joins departments or faculties."""
    return [
        ProgrammeModel.tenant_id == tenant_id,
        ProgrammeModel.status == "active",
        # The department's own faculty must be the programme's: nothing in the schema says so.
        select(DepartmentModel.id)
        .where(
            DepartmentModel.id == ProgrammeModel.department_id,
            DepartmentModel.faculty_id == ProgrammeModel.faculty_id,
            *_active_department(tenant_id),
        )
        .correlate(ProgrammeModel)
        .exists(),
    ]


def readable_course(tenant_id: str) -> list[ColumnElement[bool]]:
    """A course a student can read (listCourses, getCourse): active, under an
    active department of an active faculty."""
    return [
        CourseModel.tenant_id == tenant_id,
        CourseModel.status == CourseStatus.ACTIVE.value,
        CourseModel.department_id.in_(select(DepartmentModel.id).where(*_active_department(tenant_id))),
    ]


class SqlAlchemyCourseRepository(CourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _one_course(self, statement, for_update: bool) -> Course | None:
        """One course aggregate. For a change, its row is locked first (FOR
        UPDATE OF courses), and its topics, outcomes and materials are read
        after the lock is held, so a concurrent change to the same course
        waits and then sees what the other committed. Without the lock, two
        changes each rewrote the children from a stale copy and one was lost."""
        if for_update:
            statement = statement.with_for_update(of=CourseModel).execution_options(populate_existing=True)
        result = await self._session.scalars(statement)
        model = result.first()
        return course_to_domain(model) if model is not None else None

    async def save(self, course: Course, tenant_id: str | None = None) -> Course:
        statement = select(CourseModel).where(CourseModel.id == course.id.value)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        result = await self._session.scalars(statement)
        model = result.first()
        if model is None:
            model = course_to_model(course)
            if tenant_id is not None:
                model.tenant_id = tenant_id
            self._session.add(model)
        else:
            course_to_model(course, model=model)
            if tenant_id is not None:
                model.tenant_id = tenant_id
        await self._session.flush()
        return course

    async def has_active_department(self, department_id: str, tenant_id: str) -> bool:
        found = await self._session.scalar(
            select(DepartmentModel.id).where(DepartmentModel.id == department_id, *_active_department(tenant_id))
        )
        return found is not None

    async def _structure_page(
        self, model: type[StructureModel], conditions: list[ColumnElement[bool]], limit: int, offset: int
    ) -> tuple[list[StructureModel], int]:
        total = await self._session.scalar(select(func.count()).select_from(model).where(*conditions))
        rows = await self._session.scalars(
            select(model).where(*conditions).order_by(model.name, model.id).limit(limit).offset(offset)
        )
        return list(rows.all()), total or 0

    async def list_faculties(self, tenant_id: str, limit: int, offset: int) -> tuple[list[FacultyEntry], int]:
        rows, total = await self._structure_page(FacultyModel, _active_faculty(tenant_id), limit, offset)
        return [FacultyEntry(id=row.id, name=row.name, slug=row.slug) for row in rows], total

    async def list_departments(
        self, tenant_id: str, faculty_id: str | None, limit: int, offset: int
    ) -> tuple[list[DepartmentEntry], int]:
        conditions = _active_department(tenant_id)
        if faculty_id is not None:
            conditions.append(DepartmentModel.faculty_id == faculty_id)
        rows, total = await self._structure_page(DepartmentModel, conditions, limit, offset)
        return [DepartmentEntry(id=row.id, faculty_id=row.faculty_id, name=row.name, slug=row.slug) for row in rows], total

    async def list_programmes(
        self, tenant_id: str, department_id: str | None, limit: int, offset: int
    ) -> tuple[list[ProgrammeEntry], int]:
        conditions = readable_programme(tenant_id)
        if department_id is not None:
            conditions.append(ProgrammeModel.department_id == department_id)
        rows, total = await self._structure_page(ProgrammeModel, conditions, limit, offset)
        return [
            ProgrammeEntry(
                id=row.id,
                faculty_id=row.faculty_id,
                department_id=row.department_id,
                name=row.name,
                slug=row.slug,
                code=row.code,
                duration_years=row.duration_years,
            )
            for row in rows
        ], total

    async def get_by_id(self, course_id: str, tenant_id: str | None = None, *, for_update: bool = False) -> Course | None:
        statement = select(CourseModel).where(CourseModel.id == course_id)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        return await self._one_course(statement, for_update)

    async def list_page(
        self,
        tenant_id: str,
        department_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Course], int]:
        conditions = readable_course(tenant_id) if active_only else [CourseModel.tenant_id == tenant_id]
        if department_id is not None:
            conditions.append(CourseModel.department_id == department_id)
        total = await self._session.scalar(select(func.count()).select_from(CourseModel).where(*conditions))
        statement = (
            select(CourseModel)
            .where(*conditions)
            .order_by(CourseModel.code, CourseModel.id)
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
                selectinload(CourseModel.reference_materials),
            )
        )
        result = await self._session.scalars(statement)
        return [course_to_domain(c) for c in result.all()], total or 0

    async def get_by_topic_id(self, topic_id: str, tenant_id: str | None = None, *, for_update: bool = False) -> Course | None:
        statement = select(CourseModel).join(TopicModel, TopicModel.course_id == CourseModel.id).where(TopicModel.id == topic_id)
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        return await self._one_course(statement, for_update)

    async def get_by_learning_outcome_id(
        self, learning_outcome_id: str, tenant_id: str | None = None, *, for_update: bool = False
    ) -> Course | None:
        statement = (
            select(CourseModel)
            .join(TopicModel, TopicModel.course_id == CourseModel.id)
            .join(
                LearningOutcomeModel,
                LearningOutcomeModel.topic_id == TopicModel.id,
            )
            .where(LearningOutcomeModel.id == learning_outcome_id)
        )
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        return await self._one_course(statement, for_update)

    async def get_by_reference_material_id(
        self, reference_material_id: str, tenant_id: str | None = None, *, for_update: bool = False
    ) -> Course | None:
        statement = (
            select(CourseModel)
            .join(
                ReferenceMaterialModel,
                ReferenceMaterialModel.course_id == CourseModel.id,
            )
            .where(ReferenceMaterialModel.id == reference_material_id)
        )
        if tenant_id is not None:
            statement = statement.where(CourseModel.tenant_id == tenant_id)
        statement = statement.options(
            selectinload(CourseModel.topics).selectinload(TopicModel.learning_outcomes),
            selectinload(CourseModel.reference_materials),
        )
        return await self._one_course(statement, for_update)

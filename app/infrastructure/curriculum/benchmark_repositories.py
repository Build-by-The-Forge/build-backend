from __future__ import annotations

from app.domain.curriculum.benchmark import BenchmarkCourse, BenchmarkCurriculum
from app.domain.repositories.benchmark_curriculum import (
    BenchmarkCurriculumRepository,
)
from app.infrastructure.curriculum.benchmark_mappers import (
    benchmark_course_model_to_domain,
    benchmark_course_to_model,
    benchmark_curriculum_model_to_domain,
    benchmark_curriculum_to_model,
)
from app.infrastructure.db.models.benchmark import (
    BenchmarkCourseModel,
    BenchmarkCurriculumModel,
    BenchmarkTopicModel,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class SqlAlchemyBenchmarkCurriculumRepository(BenchmarkCurriculumRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, curriculum: BenchmarkCurriculum) -> BenchmarkCurriculum:
        statement = select(BenchmarkCurriculumModel).where(BenchmarkCurriculumModel.id == curriculum.id)
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = benchmark_curriculum_to_model(curriculum)
            self._session.add(model)
        else:
            benchmark_curriculum_to_model(curriculum, model=model)
        await self._session.flush()
        return curriculum

    async def save_course(self, course: BenchmarkCourse) -> BenchmarkCourse:
        statement = select(BenchmarkCourseModel).where(BenchmarkCourseModel.id == course.id)
        model = (await self._session.scalars(statement)).first()
        if model is None:
            model = benchmark_course_to_model(course)
            self._session.add(model)
        else:
            benchmark_course_to_model(course, model=model)
        await self._session.flush()
        return course

    async def get_by_id(self, curriculum_id: str) -> BenchmarkCurriculum | None:
        statement = select(BenchmarkCurriculumModel).where(BenchmarkCurriculumModel.id == curriculum_id)
        model = (await self._session.scalars(statement)).first()
        return benchmark_curriculum_model_to_domain(model) if model is not None else None

    async def get_by_snapshot_and_programme(self, source_snapshot_id: str, programme_code: str) -> BenchmarkCurriculum | None:
        statement = select(BenchmarkCurriculumModel).where(
            BenchmarkCurriculumModel.source_snapshot_id == source_snapshot_id,
            BenchmarkCurriculumModel.programme_code == programme_code.upper(),
        )
        model = (await self._session.scalars(statement)).first()
        return benchmark_curriculum_model_to_domain(model) if model is not None else None

    async def get_active_by_programme(
        self,
        discipline_group: str,
        programme_code: str,
        degree_level: str = "undergraduate",
    ) -> BenchmarkCurriculum | None:
        statement = select(BenchmarkCurriculumModel).where(
            BenchmarkCurriculumModel.discipline_group == discipline_group,
            BenchmarkCurriculumModel.programme_code == programme_code.upper(),
            BenchmarkCurriculumModel.degree_level == degree_level,
            BenchmarkCurriculumModel.status == "active",
        )
        model = (await self._session.scalars(statement)).first()
        return benchmark_curriculum_model_to_domain(model) if model is not None else None

    async def list_curricula(
        self,
        programme_code: str | None = None,
        status: str | None = None,
    ) -> list[BenchmarkCurriculum]:
        statement = select(BenchmarkCurriculumModel).order_by(
            BenchmarkCurriculumModel.programme_code.asc(),
            BenchmarkCurriculumModel.created_at.desc(),
        )
        if programme_code is not None:
            statement = statement.where(BenchmarkCurriculumModel.programme_code == programme_code.upper())
        if status is not None:
            statement = statement.where(BenchmarkCurriculumModel.status == status)
        models = (await self._session.scalars(statement)).all()
        return [benchmark_curriculum_model_to_domain(m) for m in models]

    async def get_course(self, course_id: str) -> BenchmarkCourse | None:
        statement = (
            select(BenchmarkCourseModel)
            .where(BenchmarkCourseModel.id == course_id)
            .options(selectinload(BenchmarkCourseModel.topics).selectinload(BenchmarkTopicModel.outcomes))
        )
        model = (await self._session.scalars(statement)).first()
        return benchmark_course_model_to_domain(model, include_topics=True) if model is not None else None

    async def get_course_by_code(self, curriculum_id: str, code: str) -> BenchmarkCourse | None:
        statement = (
            select(BenchmarkCourseModel)
            .where(
                BenchmarkCourseModel.benchmark_curriculum_id == curriculum_id,
                BenchmarkCourseModel.code == code.upper(),
            )
            .options(selectinload(BenchmarkCourseModel.topics).selectinload(BenchmarkTopicModel.outcomes))
        )
        model = (await self._session.scalars(statement)).first()
        return benchmark_course_model_to_domain(model, include_topics=True) if model is not None else None

    async def list_courses(
        self,
        curriculum_id: str,
        level: int | None = None,
        semester: int | None = None,
    ) -> list[BenchmarkCourse]:
        statement = (
            select(BenchmarkCourseModel)
            .where(BenchmarkCourseModel.benchmark_curriculum_id == curriculum_id)
            .order_by(BenchmarkCourseModel.sequence.asc())
        )
        if level is not None:
            statement = statement.where(BenchmarkCourseModel.level == level)
        if semester is not None:
            statement = statement.where(BenchmarkCourseModel.semester == semester)
        models = (await self._session.scalars(statement)).all()
        return [benchmark_course_model_to_domain(m, include_topics=False) for m in models]

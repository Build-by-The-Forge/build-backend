from typing import Protocol

from app.domain.curriculum.benchmark import BenchmarkCourse, BenchmarkCurriculum


class BenchmarkCurriculumRepository(Protocol):
    async def save(self, curriculum: BenchmarkCurriculum) -> BenchmarkCurriculum:
        raise NotImplementedError

    async def save_course(self, course: BenchmarkCourse) -> BenchmarkCourse:
        raise NotImplementedError

    async def get_by_id(self, curriculum_id: str) -> BenchmarkCurriculum | None:
        raise NotImplementedError

    async def get_by_snapshot_and_programme(
        self, source_snapshot_id: str, programme_code: str
    ) -> BenchmarkCurriculum | None:
        raise NotImplementedError

    async def list_curricula(
        self,
        programme_code: str | None = None,
        status: str | None = None,
    ) -> list[BenchmarkCurriculum]:
        raise NotImplementedError

    async def get_course(self, course_id: str) -> BenchmarkCourse | None:
        raise NotImplementedError

    async def get_course_by_code(
        self, curriculum_id: str, code: str
    ) -> BenchmarkCourse | None:
        raise NotImplementedError

    async def list_courses(
        self,
        curriculum_id: str,
        level: int | None = None,
        semester: int | None = None,
    ) -> list[BenchmarkCourse]:
        raise NotImplementedError

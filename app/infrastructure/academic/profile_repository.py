"""The academic profile on SQLAlchemy (S-02 design, "Transaction")."""

from uuid import uuid4

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.academic.profile import (
    AcademicProfile,
    NotAStudentMember,
    ProfileCourse,
    ProfileProgramme,
    ProfileUnit,
    UnavailableReferences,
)
from app.domain.repositories.academic_profile import AcademicProfileRepository
from app.domain.tenant.value_objects import MembershipRole, MembershipStatus
from app.infrastructure.catalogue.repositories import readable_course, readable_programme
from app.infrastructure.db.models.academic import AcademicProfileCourseModel, AcademicProfileModel
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    LevelModel,
    MembershipModel,
    ProgrammeModel,
)

# The column is a PostgreSQL integer: anything outside it names no level.
_INT32 = range(-(2**31), 2**31)


def _readable_level(tenant_id: str, code: int):
    return [LevelModel.tenant_id == tenant_id, LevelModel.code == code, LevelModel.status == "active"]


def _usable_id(value: str) -> bool:
    """PostgreSQL text can't hold NUL: such an ID names nothing, and isn't sent."""
    return "\x00" not in value


class SqlAlchemyAcademicProfileRepository(AcademicProfileRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_student(self, tenant_id: str, user_id: str, *, lock: bool) -> None:
        """An active student membership of the tenant, or NotAStudentMember. A
        save holds it FOR SHARE, so a role change or revocation can't commit
        while the save runs."""
        statement = select(MembershipModel.id).where(
            MembershipModel.tenant_id == tenant_id,
            MembershipModel.user_id == user_id,
            MembershipModel.role == MembershipRole.STUDENT.value,
            MembershipModel.status == MembershipStatus.ACTIVE.value,
        )
        if lock:
            statement = statement.with_for_update(read=True)
        if await self._session.scalar(statement) is None:
            raise NotAStudentMember()

    async def read(self, tenant_id: str, user_id: str) -> AcademicProfile:
        await self._require_student(tenant_id, user_id, lock=False)
        profile = await self._session.scalar(
            select(AcademicProfileModel).where(
                AcademicProfileModel.tenant_id == tenant_id, AcademicProfileModel.user_id == user_id
            )
        )
        if profile is None:
            return AcademicProfile()

        # Aliases, so readable_programme's subquery stays correlated to programmes only.
        department, faculty = aliased(DepartmentModel), aliased(FacultyModel)
        programme_row = (
            await self._session.execute(
                select(
                    ProgrammeModel.id,
                    ProgrammeModel.name,
                    ProgrammeModel.code,
                    department.id,
                    department.name,
                    faculty.id,
                    faculty.name,
                )
                .join(department, department.id == ProgrammeModel.department_id)
                .join(faculty, faculty.id == ProgrammeModel.faculty_id)
                .where(ProgrammeModel.id == profile.programme_id, *readable_programme(tenant_id))
            )
        ).first()
        level = await self._session.scalar(select(LevelModel.code).where(*_readable_level(tenant_id, profile.level_code)))
        courses = await self._session.execute(
            select(
                CourseModel.id,
                CourseModel.code,
                CourseModel.title,
                CourseModel.level,
                CourseModel.semester,
                CourseModel.credit_units,
            )
            .join(
                AcademicProfileCourseModel,
                and_(
                    AcademicProfileCourseModel.course_id == CourseModel.id,
                    AcademicProfileCourseModel.tenant_id == CourseModel.tenant_id,
                ),
            )
            .where(AcademicProfileCourseModel.profile_id == profile.id, *readable_course(tenant_id))
            .order_by(CourseModel.code, CourseModel.id)
        )
        return AcademicProfile(
            programme=ProfileProgramme(*programme_row[0:3]) if programme_row else None,
            department=ProfileUnit(*programme_row[3:5]) if programme_row else None,
            faculty=ProfileUnit(*programme_row[5:7]) if programme_row else None,
            level=level,
            courses=[ProfileCourse(*row) for row in courses.all()],
            updated_at=profile.updated_at,
        )

    async def replace(self, tenant_id: str, user_id: str, programme_id: str, level: int, course_ids: list[str]) -> None:
        await self._require_student(tenant_id, user_id, lock=True)
        # 1. Every reference, against what a student of this tenant can read.
        # Any miss refuses the save before anything is written.
        unavailable = []
        if not (
            _usable_id(programme_id)
            and await self._session.scalar(
                select(ProgrammeModel.id).where(ProgrammeModel.id == programme_id, *readable_programme(tenant_id))
            )
        ):
            unavailable.append("programme_id")
        level_query = select(LevelModel.code).where(*_readable_level(tenant_id, level))
        if level not in _INT32 or await self._session.scalar(level_query) is None:
            unavailable.append("level")
        if course_ids:
            found = set()
            if all(_usable_id(c) for c in course_ids):
                found = set(
                    await self._session.scalars(
                        select(CourseModel.id).where(CourseModel.id.in_(course_ids), *readable_course(tenant_id))
                    )
                )
            if found != set(course_ids):
                unavailable.append("course_ids")
        if unavailable:
            raise UnavailableReferences(unavailable)

        # 2. The profile row, inserted or updated in one statement, which takes
        # its row lock: of two concurrent saves, the second waits here until the
        # first commits, and of two first saves, the second becomes the update.
        upsert = postgresql_insert if self._session.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = upsert(AcademicProfileModel).values(
            id=str(uuid4()), tenant_id=tenant_id, user_id=user_id, programme_id=programme_id, level_code=level
        )
        profile_id = await self._session.scalar(
            statement.on_conflict_do_update(
                index_elements=["tenant_id", "user_id"],
                set_={"programme_id": programme_id, "level_code": level, "updated_at": func.now()},
            ).returning(AcademicProfileModel.id)
        )

        # 3. The course set, replaced whole. Run after the lock, so a waiting
        # save deletes what the first one committed.
        await self._session.execute(delete(AcademicProfileCourseModel).where(AcademicProfileCourseModel.profile_id == profile_id))
        if course_ids:
            await self._session.execute(
                insert(AcademicProfileCourseModel),
                [{"profile_id": profile_id, "tenant_id": tenant_id, "course_id": c} for c in course_ids],
            )

import uuid
from datetime import datetime, timezone

import pytest

from app.domain.catalogue.course import Course
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseId,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseTitle,
    DepartmentId,
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

    tenant = TenantModel(id=tenant_id, name="T", slug="t", created_at=now, updated_at=now, status="active")
    faculty = FacultyModel(id=faculty_id, tenant_id=tenant_id, name="F", slug="f", created_at=now, updated_at=now, status="active")
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

    await repo.save(course, tenant_id=tenant_id)

    fetched = await repo.get_by_id(course.id.value)
    assert fetched is not None
    assert str(fetched.id) == str(course.id)
    assert fetched.code.value == course.code.value

    all_courses = await repo.list_all()
    assert any(c.id.value == course.id.value for c in all_courses)

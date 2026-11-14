"""Migration 0032 on real PostgreSQL (S-02): the academic profile's schema.

The database itself keeps a profile inside its tenant, with the application
bypassed: every reference is tested with another tenant's row and with NULL,
since a composite foreign key with a NULL part checks nothing.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    LevelModel,
    MembershipModel,
    ProgrammeModel,
    TenantModel,
)
from app.infrastructure.identity.models import UserModel
from pg_smoke.test_migration_0030 import REFUSED, _id, _refused, _run, _scalar

pytestmark = pytest.mark.asyncio(loop_scope="session")

PROFILE = "INSERT INTO academic_profiles (id, tenant_id, user_id, programme_id, level_code) VALUES (:id, :t, :u, :p, :l)"
ENROLMENT = "INSERT INTO academic_profile_courses (profile_id, tenant_id, course_id) VALUES (:p, :t, :c)"


async def _world(level: int = 300) -> dict[str, str]:
    """A tenant with a faculty, department, programme, level and course, and a
    student member, built through the models so their defaults apply."""
    now = datetime.now(timezone.utc)
    stamps = {"status": "active", "created_at": now, "updated_at": now}
    tag = uuid4().hex[:8]
    w = {k: _id() for k in ("tenant", "faculty", "department", "programme", "level", "course", "user", "member")}
    rows = [
        TenantModel(id=w["tenant"], name="S02", slug=f"s02-{tag}", **stamps),
        FacultyModel(id=w["faculty"], tenant_id=w["tenant"], name="F", slug=f"f-{tag}", **stamps),
        DepartmentModel(
            id=w["department"],
            tenant_id=w["tenant"],
            faculty_id=w["faculty"],
            name="D",
            slug=f"d-{tag}",
            code=f"D{tag}",
            **stamps,
        ),
        ProgrammeModel(
            id=w["programme"],
            tenant_id=w["tenant"],
            faculty_id=w["faculty"],
            department_id=w["department"],
            name="P",
            slug=f"p-{tag}",
            code=f"P{tag}",
            duration_years=5,
            **stamps,
        ),
        LevelModel(id=w["level"], tenant_id=w["tenant"], code=level, name=f"{level} level", **stamps),
        CourseModel(
            id=w["course"],
            tenant_id=w["tenant"],
            department_id=w["department"],
            code=f"C{tag}",
            title="C",
            slug=f"c-{tag}",
            credit_units=3,
            level=level,
            semester=1,
            **stamps,
        ),
        UserModel(id=w["user"], email=f"s02-{tag}@example.com", password_hash="x"),
        MembershipModel(id=w["member"], tenant_id=w["tenant"], user_id=w["user"], role="student", **stamps),
    ]
    async with SessionLocal() as session:
        for row in rows:  # parents first, for the foreign keys
            session.add(row)
            await session.flush()
        await session.commit()
    w["level_code"] = str(level)
    return w


async def _profile(w: dict[str, str]) -> str:
    profile = _id()
    await _run(PROFILE, id=profile, t=w["tenant"], u=w["user"], p=w["programme"], l=int(w["level_code"]))
    return profile


async def test_a_profile_names_a_programme_and_level_of_its_own_tenant():
    w, other = await _world(300), await _world(700)
    # Another tenant's programme; a level code only another tenant has.
    await _refused(PROFILE, id=_id(), t=w["tenant"], u=w["user"], p=other["programme"], l=300)
    await _refused(PROFILE, id=_id(), t=w["tenant"], u=w["user"], p=w["programme"], l=700)
    for column in ("p", "l"):
        values = {"id": _id(), "t": w["tenant"], "u": w["user"], "p": w["programme"], "l": 300}
        await _refused(PROFILE, **{**values, column: None})
    await _profile(w)


async def test_a_profile_belongs_to_a_membership_of_its_tenant_and_there_is_one():
    w, other = await _world(), await _world()
    # The user has no membership in the other tenant.
    await _refused(PROFILE, id=_id(), t=other["tenant"], u=w["user"], p=other["programme"], l=300)
    await _refused(PROFILE, id=_id(), t=w["tenant"], u=None, p=w["programme"], l=300)
    await _profile(w)
    with pytest.raises(REFUSED):
        await _profile(w)


async def test_an_enrolment_keeps_its_profile_and_course_in_its_own_tenant():
    w, other = await _world(), await _world()
    mine, theirs = await _profile(w), await _profile(other)
    # Another tenant's course, under either tenant's id on the row.
    await _refused(ENROLMENT, p=mine, t=w["tenant"], c=other["course"])
    await _refused(ENROLMENT, p=mine, t=other["tenant"], c=other["course"])
    # Another tenant's profile with this tenant's course.
    await _refused(ENROLMENT, p=theirs, t=w["tenant"], c=w["course"])
    await _refused(ENROLMENT, p=mine, t=None, c=w["course"])
    await _run(ENROLMENT, p=mine, t=w["tenant"], c=w["course"])
    with pytest.raises(REFUSED):
        await _run(ENROLMENT, p=mine, t=w["tenant"], c=w["course"])  # enrolled once


async def test_removing_the_membership_removes_the_profile_and_its_courses():
    w = await _world()
    profile = await _profile(w)
    await _run(ENROLMENT, p=profile, t=w["tenant"], c=w["course"])

    await _run("DELETE FROM memberships WHERE id = :m", m=w["member"])

    assert await _scalar("SELECT count(*) FROM academic_profiles WHERE id = :p", p=profile) == 0
    assert await _scalar("SELECT count(*) FROM academic_profile_courses WHERE profile_id = :p", p=profile) == 0


async def test_a_deleted_course_leaves_its_enrolments_and_a_named_programme_or_level_stays():
    w = await _world()
    profile = await _profile(w)
    await _run(ENROLMENT, p=profile, t=w["tenant"], c=w["course"])

    await _refused("DELETE FROM programmes WHERE id = :p", p=w["programme"])
    await _refused("DELETE FROM levels WHERE id = :l", l=w["level"])
    await _run("DELETE FROM courses WHERE id = :c", c=w["course"])

    assert await _scalar("SELECT count(*) FROM academic_profile_courses WHERE profile_id = :p", p=profile) == 0
    assert await _scalar("SELECT count(*) FROM academic_profiles WHERE id = :p", p=profile) == 1

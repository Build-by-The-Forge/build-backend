"""S-02: the student's academic profile, GET and PUT /academic/profile.

Every reference is checked against what a student of the tenant can read,
any that isn't gets one answer naming only the field, a save replaces the
whole profile, and only students have one.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    LevelModel,
    MembershipModel,
    ProgrammeModel,
)
from tests.integration.assessment.test_attempt_api import add_membership
from tests.integration.assessment.test_question_api import register_and_authenticate
from tests.integration.catalogue.test_academic_structure import Institution, add_row, institution
from tests.integration.catalogue.test_tenant_scoped_mutations import headers

PATH = "/academic/profile"
MARKER = "marker-7f3c"


class School:
    """An institution with one programme, two levels and three courses, and
    a student of it."""

    def __init__(self, inst: Institution, student: dict) -> None:
        self.inst = inst
        self.student = student

    @classmethod
    async def create(cls, client, role: str = "student") -> "School":
        inst, member = await institution(client, role)
        school = cls(inst, member)
        school.faculty = await inst.school("School of Computing")
        school.department = await inst.department(school.faculty, "Computer Science")
        school.programme = await inst.programme(school.faculty, school.department, "B.Tech. Computer Science")
        school.levels = {code: await school.level(code) for code in (300, 400)}
        school.courses = [await school.course(code) for code in ("CSC 305", "CSC 301", "MTH 301")]
        return school

    def _stamps(self, status: str = "active") -> dict:
        now = datetime.now(timezone.utc)
        return {"id": str(uuid4()), "tenant_id": self.inst.tenant_id, "status": status, "created_at": now, "updated_at": now}

    async def level(self, code: int, status: str = "active") -> str:
        return await add_row(LevelModel(code=code, name=f"{code} level", **self._stamps(status)))

    async def course(self, code: str, department: str | None = None, status: str = "active") -> str:
        return await add_row(
            CourseModel(
                department_id=department or self.department,
                code=code,
                title=f"{code} title",
                slug=f"c-{uuid4().hex[:10]}",
                credit_units=3,
                level=300,
                semester=1,
                **self._stamps(status),
            )
        )

    def body(self, **overrides) -> dict:
        return {"programme_id": self.programme, "level": 300, "course_ids": self.courses[:2], **overrides}


async def set_status(model, row_id: str, status: str) -> None:
    async with SessionLocal() as session:
        await session.execute(update(model).where(model.id == row_id).values(status=status))
        await session.commit()


def data(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()["data"]


EMPTY = {
    "programme": None,
    "department": None,
    "faculty": None,
    "level": None,
    "courses": [],
    "complete": False,
    "updated_at": None,
}


@pytest.mark.asyncio
async def test_before_the_first_save_every_field_is_empty(client):
    school = await School.create(client)

    assert data(client.get(PATH, headers=school.student)) == EMPTY


@pytest.mark.asyncio
async def test_a_save_reads_back_with_department_and_faculty_from_the_programme(client):
    school = await School.create(client)

    saved = data(client.put(PATH, json=school.body(course_ids=school.courses), headers=school.student))
    read = data(client.get(PATH, headers=school.student))

    assert saved == read
    assert read["programme"] == {"id": school.programme, "name": "B.Tech. Computer Science", "code": read["programme"]["code"]}
    assert read["department"] == {"id": school.department, "name": "Computer Science"}
    assert read["faculty"] == {"id": school.faculty, "name": "School of Computing"}
    assert read["level"] == 300 and read["complete"] is True and read["updated_at"]
    # Ordered by code, then id.
    assert [c["code"] for c in read["courses"]] == ["CSC 301", "CSC 305", "MTH 301"]
    assert set(read["courses"][0]) == {"id", "code", "title", "level", "semester", "credit_units"}
    assert set(read) == set(EMPTY)


@pytest.mark.asyncio
async def test_a_save_replaces_the_whole_profile(client):
    school = await School.create(client)
    client.put(PATH, json=school.body(course_ids=school.courses), headers=school.student)

    data(client.put(PATH, json=school.body(level=400, course_ids=[school.courses[2]]), headers=school.student))
    read = data(client.get(PATH, headers=school.student))
    assert read["level"] == 400 and [c["id"] for c in read["courses"]] == [school.courses[2]]

    data(client.put(PATH, json=school.body(course_ids=[]), headers=school.student))
    assert data(client.get(PATH, headers=school.student))["courses"] == []


async def _unavailable(school: School, other: School, case: str) -> dict:
    """A body naming one reference the student can't read, and its field."""
    if case == "unknown programme":
        return school.body(programme_id=str(uuid4()))
    if case == "another tenant's programme":
        return school.body(programme_id=other.programme)
    if case == "archived programme":
        await set_status(ProgrammeModel, school.programme, "archived")
    if case == "programme of an archived department":
        await set_status(DepartmentModel, school.department, "archived")
    if case == "programme of an archived faculty":
        await set_status(FacultyModel, school.faculty, "archived")
    if case.endswith("programme") or "programme of" in case:
        return school.body(course_ids=[])
    if case == "unknown level":
        return school.body(level=500)
    if case == "another tenant's level":
        await other.level(700)
        return school.body(level=700)
    if case == "archived level":
        await set_status(LevelModel, school.levels[300], "archived")
        return school.body()
    if case == "level outside the column":
        return school.body(level=2**40)
    if case == "unknown course":
        return school.body(course_ids=[school.courses[0], str(uuid4())])
    if case == "another tenant's course":
        return school.body(course_ids=[other.courses[0]])
    if case == "archived course":
        await set_status(CourseModel, school.courses[0], "archived")
        return school.body()
    if case == "course of an archived department":
        elsewhere = await school.inst.department(school.faculty, "Mathematics", status="archived")
        return school.body(course_ids=[await school.course("MTH 399", department=elsewhere)])
    if case == "an id holding a NUL":
        return school.body(course_ids=[f"{MARKER}\x00"])
    raise AssertionError(case)


FIELD = {"programme": "programme_id", "level": "level", "course": "course_ids", "NUL": "course_ids"}
CASES = [
    "unknown programme",
    "another tenant's programme",
    "archived programme",
    "programme of an archived department",
    "programme of an archived faculty",
    "unknown level",
    "another tenant's level",
    "archived level",
    "level outside the column",
    "unknown course",
    "another tenant's course",
    "archived course",
    "course of an archived department",
    "an id holding a NUL",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES)
async def test_anything_a_student_cant_read_gets_one_answer_naming_its_field(client, case):
    school, other = await School.create(client), await School.create(client)
    body = await _unavailable(school, other, case)

    response = client.put(PATH, json=body, headers=school.student)

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    field = next(v for k, v in FIELD.items() if k in case)
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"] == {"fields": [{"field": f"body.{field}", "code": "value_error", "message": "is not available"}]}
    assert MARKER not in response.text
    # Nothing was written.
    assert data(client.get(PATH, headers=school.student)) == EMPTY


@pytest.mark.asyncio
async def test_every_unavailable_field_is_named_at_once(client):
    school = await School.create(client)

    response = client.put(
        PATH, json={"programme_id": str(uuid4()), "level": 999, "course_ids": [str(uuid4())]}, headers=school.student
    )

    fields = [f["field"] for f in response.json()["error"]["details"]["fields"]]
    assert fields == ["body.programme_id", "body.level", "body.course_ids"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"extra": MARKER},
        {"programme_id": None},
        {"programme_id": ""},
        {"programme_id": "x" * 37},
        {"level": "300"},
        {"level": True},
        {"level": 300.5},
        {"course_ids": MARKER},
        {"course_ids": [MARKER, MARKER]},
        {"course_ids": [str(uuid4()) for _ in range(31)]},
    ],
)
async def test_a_malformed_body_is_refused_without_echoing_it(client, change):
    school = await School.create(client)

    response = client.put(PATH, json={**school.body(), **change}, headers=school.student)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert MARKER not in response.text
    assert data(client.get(PATH, headers=school.student)) == EMPTY


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["programme_id", "level", "course_ids"])
async def test_every_field_is_required(client, missing):
    school = await School.create(client)
    body = school.body()
    del body[missing]

    assert client.put(PATH, json=body, headers=school.student).status_code == 422


@pytest.mark.asyncio
async def test_thirty_courses_are_accepted(client):
    school = await School.create(client)
    courses = [await school.course(f"GST {100 + i}") for i in range(30)]

    assert len(data(client.put(PATH, json=school.body(course_ids=courses), headers=school.student))["courses"]) == 30


@pytest.mark.asyncio
async def test_what_is_archived_after_saving_is_hidden_and_comes_back_when_restored(client):
    school = await School.create(client)
    client.put(PATH, json=school.body(), headers=school.student)

    await set_status(CourseModel, school.courses[0], "archived")
    assert [c["id"] for c in data(client.get(PATH, headers=school.student))["courses"]] == [school.courses[1]]
    await set_status(CourseModel, school.courses[0], "active")
    assert len(data(client.get(PATH, headers=school.student))["courses"]) == 2

    await set_status(ProgrammeModel, school.programme, "archived")
    read = data(client.get(PATH, headers=school.student))
    assert read["programme"] is None and read["department"] is None and read["faculty"] is None
    assert read["complete"] is False and read["level"] == 300

    await set_status(ProgrammeModel, school.programme, "active")
    await set_status(LevelModel, school.levels[300], "archived")
    read = data(client.get(PATH, headers=school.student))
    assert read["level"] is None and read["complete"] is False and read["programme"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["lecturer", "hod", "faculty_admin", "admin", "owner"])
async def test_a_staff_membership_is_refused_on_both_routes(client, role):
    school = await School.create(client, role=role)

    for response in (client.get(PATH, headers=school.student), client.put(PATH, json=school.body(), headers=school.student)):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_who_reaches_the_profile(client):
    school = await School.create(client)
    outsider_id, outsider_token = await register_and_authenticate(client, f"outsider-{uuid4()}@example.com")
    assert outsider_id

    for method in ("GET", "PUT"):
        assert client.request(method, PATH).status_code == 401
        assert client.request(method, PATH, headers={"Authorization": school.student["Authorization"]}).status_code == 400
        refused = client.request(method, PATH, json=school.body(), headers=headers(outsider_token, school.inst.slug))
        assert refused.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    async with SessionLocal() as session:
        await session.execute(
            update(MembershipModel).where(MembershipModel.tenant_id == school.inst.tenant_id).values(status="archived")
        )
        await session.commit()
    assert client.get(PATH, headers=school.student).json()["error"]["code"] == "TENANT_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_each_student_has_their_own_profile_in_each_tenant(client):
    first, second = await School.create(client), await School.create(client)
    client.put(PATH, json=first.body(), headers=first.student)

    assert data(client.get(PATH, headers=second.student)) == EMPTY
    # The same user in another tenant starts empty too.
    user_id = client.get("/identity/me", headers={"Authorization": first.student["Authorization"]}).json()["data"]["id"]
    await add_membership(user_id, second.inst.tenant_id, "student")
    elsewhere = headers(first.student["Authorization"].removeprefix("Bearer "), second.inst.slug)
    assert data(client.get(PATH, headers=elsewhere)) == EMPTY

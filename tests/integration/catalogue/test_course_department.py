"""A course belongs to a department of its own institution."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.catalogue import CourseModel
from app.infrastructure.db.models.tenant_core import DepartmentModel, FacultyModel
from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


def new_course(client, staff: dict, department_id: str, code: str):
    return client.post(
        "/catalogue/courses/",
        headers=staff,
        json={
            "department_id": department_id,
            "code": code,
            "title": "Calculus One",
            "slug": f"calculus-{uuid4().hex[:6]}",
            "credit_units": 3,
            "level": 100,
            "semester": 1,
        },
    )


def assert_department_refused(response) -> None:
    assert response.status_code == 422, response.text
    assert response.json()["error"]["message"] == "department not found"


async def stored(code: str, tenant_id: str) -> list[str]:
    async with SessionLocal() as session:
        rows = await session.scalars(select(CourseModel.id).where(CourseModel.code == code, CourseModel.tenant_id == tenant_id))
        return list(rows.all())


@pytest.mark.asyncio
async def test_another_institutions_department_is_refused_as_if_it_didnt_exist(client):
    tenant_id, slug, _, _, token = await seed_course_context(client, "admin")
    _, _, their_department, _, _ = await seed_course_context(client, "admin")

    foreign = new_course(client, headers(token, slug), their_department, "FOR101")
    unknown = new_course(client, headers(token, slug), str(uuid4()), "UNK101")

    assert_department_refused(foreign)
    assert_department_refused(unknown)
    assert foreign.json()["error"] == {**unknown.json()["error"]}
    assert await stored("FOR101", tenant_id) == []
    assert await stored("UNK101", tenant_id) == []


@pytest.mark.asyncio
async def test_an_inactive_department_takes_no_new_courses(client):
    _, slug, department_id, _, token = await seed_course_context(client, "admin")
    async with SessionLocal() as session:
        department = await session.get(DepartmentModel, department_id)
        department.status = "archived"
        await session.commit()

    assert_department_refused(new_course(client, headers(token, slug), department_id, "OLD101"))


@pytest.mark.asyncio
async def test_a_department_of_ones_own_is_accepted(client):
    tenant_id, slug, department_id, _, token = await seed_course_context(client, "admin")

    created = new_course(client, headers(token, slug), department_id, "OWN101")

    assert created.status_code == 201, created.text
    assert len(await stored("OWN101", tenant_id)) == 1


@pytest.mark.asyncio
async def test_an_active_department_under_an_archived_faculty_takes_no_new_courses(client):
    # Readers can't see this department, so a course must not be able to join it.
    tenant_id, slug, department_id, _, token = await seed_course_context(client, "admin")
    async with SessionLocal() as session:
        department = await session.get(DepartmentModel, department_id)
        assert department.status == "active"
        faculty = await session.get(FacultyModel, department.faculty_id)
        faculty.status = "archived"
        await session.commit()

    assert_department_refused(new_course(client, headers(token, slug), department_id, "PAR101"))
    assert await stored("PAR101", tenant_id) == []

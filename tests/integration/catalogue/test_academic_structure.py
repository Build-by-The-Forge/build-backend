"""Faculties, departments and programmes: the institution's real hierarchy, for its own
members only, in the contract's order and pages."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import (
    DepartmentModel,
    FacultyModel,
    ProgrammeModel,
    TenantModel,
)
from tests.integration.assessment.test_attempt_api import add_membership
from tests.integration.assessment.test_question_api import register_and_authenticate
from tests.integration.catalogue.test_tenant_scoped_mutations import headers


async def add_row(row):
    async with SessionLocal() as session:
        session.add(row)
        await session.commit()
    return row.id


class Institution:
    """Writes the structure directly: no route creates it, provisioning does."""

    def __init__(self, tenant_id: str, slug: str) -> None:
        self.tenant_id = tenant_id
        self.slug = slug

    def _common(self, status: str) -> dict:
        now = datetime.now(timezone.utc)
        return {"id": str(uuid4()), "tenant_id": self.tenant_id, "status": status, "created_at": now, "updated_at": now}

    async def school(self, name: str, status: str = "active") -> str:
        return await add_row(FacultyModel(name=name, slug=f"s-{uuid4().hex[:10]}", **self._common(status)))

    async def department(self, school: str, name: str, status: str = "active") -> str:
        return await add_row(
            DepartmentModel(
                faculty_id=school,
                name=name,
                slug=f"d-{uuid4().hex[:10]}",
                code=f"D{uuid4().hex[:8]}",
                **self._common(status),
            )
        )

    async def programme(self, school: str, department: str, name: str, years: int = 5, status: str = "active") -> str:
        return await add_row(
            ProgrammeModel(
                faculty_id=school,
                department_id=department,
                name=name,
                slug=f"p-{uuid4().hex[:10]}",
                code=f"P{uuid4().hex[:8]}",
                duration_years=years,
                **self._common(status),
            )
        )


async def institution(client, role: str = "student"):
    tenant_id, slug = str(uuid4()), f"inst-{uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    await add_row(TenantModel(id=tenant_id, name="Institution", slug=slug, status="active", created_at=now, updated_at=now))
    user_id, token = await register_and_authenticate(client, f"structure-{uuid4()}@example.com")
    await add_membership(user_id, tenant_id, role)
    return Institution(tenant_id, slug), headers(token, slug)


def names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["data"]]


@pytest.mark.asyncio
async def test_a_futa_shaped_hierarchy_comes_back_as_it_is(client):
    futa, reader = await institution(client)
    computing = await futa.school("School of Computing")
    engineering = await futa.school("School of Engineering and Engineering Technology")
    software = await futa.department(computing, "Department of Software Engineering")
    cyber = await futa.department(computing, "Department of Cyber Security")
    mechanical = await futa.department(engineering, "Department of Mechanical Engineering")
    await futa.programme(computing, software, "B.Tech. Software Engineering", years=4)
    await futa.programme(engineering, mechanical, "B.Eng. Mechanical Engineering", years=5)

    assert names(client.get("/catalogue/faculties", headers=reader)) == [
        "School of Computing",
        "School of Engineering and Engineering Technology",
    ]
    assert names(client.get(f"/catalogue/departments?faculty_id={computing}", headers=reader)) == [
        "Department of Cyber Security",
        "Department of Software Engineering",
    ]
    assert cyber in [item["id"] for item in client.get("/catalogue/departments", headers=reader).json()["data"]]

    programmes = client.get(f"/catalogue/programmes?department_id={software}", headers=reader).json()["data"]
    assert len(programmes) == 1
    assert programmes[0]["name"] == "B.Tech. Software Engineering"
    assert programmes[0]["faculty_id"] == computing
    assert programmes[0]["department_id"] == software
    assert programmes[0]["duration_years"] == 4


@pytest.mark.asyncio
async def test_same_named_departments_of_different_schools_stay_distinct(client):
    futa, reader = await institution(client)
    first, second = await futa.school("School of Agriculture"), await futa.school("School of Sciences")
    in_first = await futa.department(first, "Department of Biology")
    in_second = await futa.department(second, "Department of Biology")

    listed = client.get("/catalogue/departments", headers=reader).json()["data"]
    assert {(item["id"], item["faculty_id"]) for item in listed} == {(in_first, first), (in_second, second)}

    narrowed = client.get(f"/catalogue/departments?faculty_id={second}", headers=reader).json()["data"]
    assert [item["id"] for item in narrowed] == [in_second]


@pytest.mark.asyncio
async def test_each_body_is_exactly_the_contracts_shape(client):
    futa, reader = await institution(client)
    school = await futa.school("School of Computing")
    department = await futa.department(school, "Department of Software Engineering")
    await futa.programme(school, department, "B.Tech. Software Engineering")

    for path, keys in (
        ("/catalogue/faculties", {"id", "name", "slug"}),
        ("/catalogue/departments", {"id", "faculty_id", "name", "slug"}),
        ("/catalogue/programmes", {"id", "faculty_id", "department_id", "name", "slug", "code", "duration_years"}),
    ):
        response = client.get(path, headers=reader, follow_redirects=False)
        assert response.status_code == 200, path
        assert set(response.json()["data"][0]) == keys, path
        assert response.json()["meta"]["pagination"] == {"total": 1, "limit": 50, "offset": 0}, path


@pytest.mark.asyncio
async def test_lists_order_by_name_and_page_over_everything_once(client):
    futa, reader = await institution(client)
    school = await futa.school("School of Computing")
    for name in ("Delta", "Alpha", "Charlie", "Bravo"):
        await futa.department(school, name)

    first = client.get("/catalogue/departments?limit=3&offset=0", headers=reader)
    second = client.get("/catalogue/departments?limit=3&offset=3", headers=reader)

    assert names(first) + names(second) == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert first.json()["meta"]["pagination"] == {"total": 4, "limit": 3, "offset": 0}
    assert second.json()["meta"]["pagination"] == {"total": 4, "limit": 3, "offset": 3}


@pytest.mark.asyncio
async def test_identical_names_keep_one_order_across_pages(client):
    futa, reader = await institution(client)
    school = await futa.school("School of Computing")
    ids = sorted([await futa.department(school, "Same name") for _ in range(3)])

    seen = [
        client.get(f"/catalogue/departments?limit=1&offset={offset}", headers=reader).json()["data"][0]["id"]
        for offset in range(3)
    ]

    assert seen == ids


@pytest.mark.asyncio
async def test_whats_inactive_is_hidden_along_with_everything_under_it(client):
    futa, reader = await institution(client)
    kept = await futa.school("Kept school")
    closed = await futa.school("Closed school", status="archived")
    kept_department = await futa.department(kept, "Kept department")
    closed_department = await futa.department(kept, "Closed department", status="archived")
    under_closed_school = await futa.department(closed, "Under closed school")
    await futa.programme(kept, kept_department, "Kept programme")
    await futa.programme(kept, kept_department, "Closed programme", status="archived")
    await futa.programme(kept, closed_department, "Under closed department")
    await futa.programme(closed, under_closed_school, "Under closed school programme")

    faculties = client.get("/catalogue/faculties", headers=reader)
    departments = client.get("/catalogue/departments", headers=reader)
    programmes = client.get("/catalogue/programmes", headers=reader)

    assert names(faculties) == ["Kept school"]
    assert names(departments) == ["Kept department"]
    assert names(programmes) == ["Kept programme"]
    for response in (faculties, departments, programmes):
        assert response.json()["meta"]["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_a_filter_naming_something_inactive_or_unknown_is_empty_not_everything(client):
    futa, reader = await institution(client)
    kept = await futa.school("Kept school")
    closed = await futa.school("Closed school", status="archived")
    department = await futa.department(kept, "Kept department")
    await futa.programme(kept, department, "Kept programme")

    for path in (
        f"/catalogue/departments?faculty_id={closed}",
        "/catalogue/departments?faculty_id=not-a-faculty",
        "/catalogue/departments?faculty_id=",
        "/catalogue/programmes?department_id=not-a-department",
        "/catalogue/programmes?department_id=",
    ):
        response = client.get(path, headers=reader)
        assert names(response) == [], path
        assert response.json()["meta"]["pagination"]["total"] == 0, path


@pytest.mark.asyncio
async def test_another_institutions_structure_cant_be_seen_or_counted(client):
    ours, our_reader = await institution(client)
    theirs, their_reader = await institution(client)
    their_school = await theirs.school("Their school")
    their_department = await theirs.department(their_school, "Their department")
    await theirs.programme(their_school, their_department, "Their programme")

    for path in (
        "/catalogue/faculties",
        "/catalogue/departments",
        "/catalogue/programmes",
        f"/catalogue/departments?faculty_id={their_school}",
        f"/catalogue/programmes?department_id={their_department}",
    ):
        response = client.get(path, headers=our_reader)
        assert names(response) == [], path
        assert response.json()["meta"]["pagination"]["total"] == 0, path
        assert "Their" not in response.text, path

    assert names(client.get("/catalogue/faculties", headers=their_reader)) == ["Their school"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/catalogue/faculties", "/catalogue/departments", "/catalogue/programmes"])
async def test_who_may_read(client, path):
    futa, reader = await institution(client)
    outsider_id, outsider_token = await register_and_authenticate(client, f"outsider-{uuid4()}@example.com")
    assert outsider_id

    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": reader["Authorization"]}).status_code == 400
    assert client.get(path, headers=headers(outsider_token, futa.slug)).status_code == 403
    assert client.get(path, headers=reader).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/catalogue/faculties", "/catalogue/departments", "/catalogue/programmes"])
async def test_limits_and_offsets_at_their_boundaries(client, path):
    _, reader = await institution(client)

    for query in ("limit=0", "limit=101", "limit=x", "offset=-1"):
        refused = client.get(f"{path}?{query}", headers=reader)
        assert refused.status_code == 422, query
        assert refused.json()["error"]["code"] == "VALIDATION_FAILED", query
    assert client.get(f"{path}?limit=1", headers=reader).status_code == 200
    assert client.get(f"{path}?limit=100", headers=reader).status_code == 200

    empty = client.get(f"{path}?offset=1000", headers=reader)
    assert empty.json()["data"] == []
    assert empty.json()["meta"]["pagination"] == {"total": 0, "limit": 50, "offset": 1000}


@pytest.mark.asyncio
async def test_a_programme_whose_faculty_and_department_disagree_isnt_served(client):
    futa, reader = await institution(client)
    computing, sciences = await futa.school("School of Computing"), await futa.school("School of Sciences")
    software = await futa.department(computing, "Department of Software Engineering")
    await futa.programme(computing, software, "Consistent")
    await futa.programme(sciences, software, "Contradictory")

    listed = client.get("/catalogue/programmes", headers=reader)

    assert names(listed) == ["Consistent"]
    assert listed.json()["meta"]["pagination"]["total"] == 1

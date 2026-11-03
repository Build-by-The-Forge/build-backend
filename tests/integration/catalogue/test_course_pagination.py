"""The course list against the contract: path, order, limits, offsets, filters and tenants."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import DepartmentModel
from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


def add_course(client, staff: dict, department_id: str, code: str) -> str:
    created = client.post(
        "/catalogue/courses/",
        headers=staff,
        json={
            "department_id": department_id,
            "code": code,
            "title": f"Course {code}",
            "slug": f"{code.lower()}-{uuid4().hex[:6]}",
            "credit_units": 3,
            "level": 100,
            "semester": 1,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


async def tenant_with_courses(client, *codes: str):
    """The seed's own course has a code starting M. These sort around it."""
    tenant_id, slug, department_id, seeded, token = await seed_course_context(client, "admin")
    staff = headers(token, slug)
    for code in codes:
        add_course(client, staff, department_id, code)
    return tenant_id, staff, department_id, seeded


def codes(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["code"] for item in response.json()["data"]]


@pytest.mark.asyncio
async def test_the_contracts_path_answers_without_a_redirect(client):
    _, staff, _, _ = await tenant_with_courses(client)

    response = client.get("/catalogue/courses", headers=staff, follow_redirects=False)

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_the_old_path_still_answers(client):
    _, staff, _, _ = await tenant_with_courses(client)

    assert client.get("/catalogue/courses/", headers=staff, follow_redirects=False).status_code == 200


@pytest.mark.asyncio
async def test_courses_come_in_code_order_whatever_order_they_were_added(client):
    _, staff, _, _ = await tenant_with_courses(client, "ZOO101", "ABC101", "CHM101")

    listed = codes(client.get("/catalogue/courses", headers=staff))

    assert listed == sorted(listed)
    assert listed[0] == "ABC101" and listed[-1] == "ZOO101"


@pytest.mark.asyncio
async def test_pages_cover_everything_once_and_report_the_total(client):
    _, staff, _, _ = await tenant_with_courses(client, "AAA101", "BBB101", "CCC101", "DDD101")

    seen: list[str] = []
    for offset in (0, 2, 4):
        response = client.get(f"/catalogue/courses?limit=2&offset={offset}", headers=staff)
        seen += codes(response)
        assert response.json()["meta"]["pagination"] == {"total": 5, "limit": 2, "offset": offset}

    assert len(seen) == 5
    assert seen == sorted(set(seen))


@pytest.mark.asyncio
async def test_defaults_and_the_largest_page_allowed(client):
    _, staff, _, _ = await tenant_with_courses(client)

    default = client.get("/catalogue/courses", headers=staff).json()["meta"]["pagination"]
    largest = client.get("/catalogue/courses?limit=100", headers=staff)

    assert default == {"total": 1, "limit": 50, "offset": 0}
    assert largest.status_code == 200


@pytest.mark.asyncio
async def test_an_offset_past_the_end_is_an_empty_page_with_the_true_total(client):
    _, staff, _, _ = await tenant_with_courses(client)

    response = client.get("/catalogue/courses?offset=50", headers=staff)

    assert codes(response) == []
    assert response.json()["meta"]["pagination"] == {"total": 1, "limit": 50, "offset": 50}


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "limit=many", "offset=-1", "offset=first"])
async def test_invalid_limits_and_offsets_are_refused(client, query):
    _, staff, _, _ = await tenant_with_courses(client)

    response = client.get(f"/catalogue/courses?{query}", headers=staff)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_the_department_filter_narrows_the_list_and_the_total(client):
    tenant_id, staff, department_id, _ = await tenant_with_courses(client, "AAA101")
    other_id = str(uuid4())
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        first = await session.get(DepartmentModel, department_id)
        session.add(
            DepartmentModel(
                id=other_id,
                tenant_id=tenant_id,
                faculty_id=first.faculty_id,
                name="Other",
                slug=f"other-{uuid4().hex[:6]}",
                code=f"O{uuid4().hex[:6].upper()}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    add_course(client, staff, other_id, "BBB101")

    response = client.get(f"/catalogue/courses?department_id={other_id}", headers=staff)

    assert codes(response) == ["BBB101"]
    assert response.json()["meta"]["pagination"]["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("department_id", ["", "not-a-department"])
async def test_a_filter_matching_nothing_is_empty_not_everything(client, department_id):
    _, staff, _, _ = await tenant_with_courses(client)

    response = client.get(f"/catalogue/courses?department_id={department_id}", headers=staff)

    assert codes(response) == []
    assert response.json()["meta"]["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_another_tenants_department_filter_shows_nothing_and_counts_nothing(client):
    _, staff, _, _ = await tenant_with_courses(client)
    _, _, their_department, _ = await tenant_with_courses(client)

    response = client.get(f"/catalogue/courses?department_id={their_department}", headers=staff)

    assert codes(response) == []
    assert response.json()["meta"]["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_each_tenant_counts_only_its_own_courses(client):
    _, ours, _, _ = await tenant_with_courses(client, "AAA101")
    _, theirs, _, _ = await tenant_with_courses(client, "BBB101", "CCC101")

    assert client.get("/catalogue/courses", headers=ours).json()["meta"]["pagination"]["total"] == 2
    assert client.get("/catalogue/courses", headers=theirs).json()["meta"]["pagination"]["total"] == 3


@pytest.mark.asyncio
async def test_archived_courses_arent_counted_unless_asked_for(client):
    _, staff, _, seeded = await tenant_with_courses(client, "AAA101")
    assert client.post(f"/catalogue/courses/{seeded}/archive", headers=staff).status_code == 200

    default = client.get("/catalogue/courses", headers=staff).json()["meta"]["pagination"]["total"]
    everything = client.get("/catalogue/courses?include_archived=true", headers=staff).json()["meta"]["pagination"]["total"]

    assert (default, everything) == (1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/catalogue/courses", "/catalogue/faculties", "/catalogue/departments", "/catalogue/programmes"],
)
async def test_the_largest_offset_is_accepted_and_past_it_is_refused(client, path):
    _, staff, _, _ = await tenant_with_courses(client)

    assert client.get(f"{path}?offset=2147483647", headers=staff).status_code == 200
    for offset in ("2147483648", "9223372036854775808", "99999999999999999999999999"):
        refused = client.get(f"{path}?offset={offset}", headers=staff)
        assert refused.status_code == 422, offset
        assert refused.json()["error"]["code"] == "VALIDATION_FAILED", offset

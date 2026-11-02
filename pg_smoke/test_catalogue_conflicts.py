"""Catalogue writes and the course list on the schema production gets. The constraints only
really race here: two requests for one code get one course and one conflict, never a 500."""

import asyncio
from uuid import uuid4

import pytest

from pg_smoke.test_academic_structure import institution

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _course(department_id: str, code: str, slug: str | None = None) -> dict:
    return {
        "department_id": department_id,
        "code": code,
        "title": f"Course {code}",
        "slug": slug or f"{code.lower()}-{uuid4().hex[:6]}",
        "credit_units": 3,
        "level": 100,
        "semester": 1,
    }


async def test_racing_requests_for_one_course_code_get_one_course_and_one_conflict(client):
    outcomes = []
    for attempt in range(5):
        staff, ids = await institution(client, "admin")
        responses = await asyncio.gather(
            client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], f"RAC{attempt}01")),
            client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], f"RAC{attempt}01")),
        )
        outcomes.append(sorted(response.status_code for response in responses))
        listed = await client.get("/catalogue/courses", headers=staff)
        assert listed.json()["meta"]["pagination"]["total"] == 1

    assert all(codes == [201, 409] for codes in outcomes), outcomes


async def test_a_taken_code_slug_and_topic_sequence_are_conflicts(client):
    staff, ids = await institution(client, "admin")
    created = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "MTH101", "calculus"))
    assert created.status_code == 201, created.text
    course_id = created.json()["data"]["id"]

    code = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "MTH101"))
    slug = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "MTH102", "calculus"))
    assert (code.status_code, slug.status_code) == (409, 409)

    topic = {"title": "Limits", "slug": "limits", "sequence": 1}
    assert (await client.post(f"/catalogue/courses/{course_id}/topics", headers=staff, json=topic)).status_code == 201
    again = await client.post(f"/catalogue/courses/{course_id}/topics", headers=staff, json={**topic, "slug": "limits-two"})
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "CONFLICT"


async def test_another_institutions_department_is_refused(client):
    staff, _ = await institution(client, "admin")
    _, theirs = await institution(client, "admin")

    refused = await client.post("/catalogue/courses/", headers=staff, json=_course(theirs["department"], "FOR101"))

    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["message"] == "department not found"


async def test_the_course_list_pages_on_the_migrated_schema(client):
    staff, ids = await institution(client, "admin")
    for code in ("ZOO101", "ABC101", "MTH101"):
        created = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], code))
        assert created.status_code == 201, created.text

    for _ in range(7):
        first = await client.get("/catalogue/courses?limit=2", headers=staff)
        second = await client.get(f"/catalogue/courses?limit=2&offset=2&department_id={ids['department']}", headers=staff)

        assert [item["code"] for item in first.json()["data"]] == ["ABC101", "MTH101"]
        assert [item["code"] for item in second.json()["data"]] == ["ZOO101"]
        assert first.json()["meta"]["pagination"] == {"total": 3, "limit": 2, "offset": 0}
        assert second.json()["meta"]["pagination"] == {"total": 3, "limit": 2, "offset": 2}

"""Catalogue writes and the course list on the schema production gets. The constraints only
really race here: two requests for one code get one course and one conflict, never a 500."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
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


async def test_two_racing_topics_on_one_sequence_get_one_topic_and_one_conflict(client):
    outcomes = []
    for _ in range(5):
        staff, ids = await institution(client, "admin")
        created = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "TOP101"))
        course_id = created.json()["data"]["id"]
        responses = await asyncio.gather(
            *(
                client.post(
                    f"/catalogue/courses/{course_id}/topics",
                    headers=staff,
                    json={"title": "Limits", "slug": f"limits-{suffix}", "sequence": 1},
                )
                for suffix in ("a", "b")
            )
        )
        outcomes.append(sorted(response.status_code for response in responses))

    assert all(codes == [201, 409] for codes in outcomes), outcomes


async def test_two_racing_topics_on_different_sequences_both_survive(client):
    staff, ids = await institution(client, "admin")
    created = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "TOP102"))
    course_id = created.json()["data"]["id"]

    responses = await asyncio.gather(
        *(
            client.post(
                f"/catalogue/courses/{course_id}/topics",
                headers=staff,
                json={"title": "Limits", "slug": f"limits-{sequence}", "sequence": sequence},
            )
            for sequence in (1, 2, 3, 4)
        )
    )

    assert [response.status_code for response in responses] == [201, 201, 201, 201]
    listed = await client.get(f"/catalogue/courses/{course_id}/topics", headers=staff)
    assert [item["sequence"] for item in listed.json()["data"]] == [1, 2, 3, 4]


async def test_a_department_under_an_archived_faculty_takes_no_course_and_hides_its_own(client):
    staff, ids = await institution(client, "admin")
    created = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "HID101"))
    course_id = created.json()["data"]["id"]
    async with SessionLocal() as session:
        await session.execute(text("update faculties set status = 'archived' where id = :id"), {"id": ids["school"]})
        await session.commit()

    refused = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "HID102"))
    listed = await client.get("/catalogue/courses", headers=staff)
    everything = await client.get("/catalogue/courses?include_archived=true", headers=staff)

    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["message"] == "department not found"
    assert listed.json()["meta"]["pagination"]["total"] == 0
    assert [item["id"] for item in everything.json()["data"]] == [course_id]


async def test_input_postgresql_cant_hold_is_refused_not_a_server_error(client):
    staff, ids = await institution(client, "admin")
    created = await client.post("/catalogue/courses/", headers=staff, json=_course(ids["department"], "NUL101"))
    course_id = created.json()["data"]["id"]
    topic = await client.post(
        f"/catalogue/courses/{course_id}/topics", headers=staff, json={"title": "Limits", "slug": "limits", "sequence": 1}
    )
    topic_id = topic.json()["data"]["id"]

    for path in (
        "/catalogue/courses?offset=9223372036854775808",
        "/catalogue/faculties?offset=99999999999999999999999999",
        "/catalogue/courses?department_id=%00",
        "/catalogue/departments?faculty_id=%00",
        "/catalogue/programmes?department_id=%00",
        "/catalogue/courses/%00",
        "/catalogue/courses/%00/topics",
        "/catalogue/topics/%00/learning-outcomes",
        "/catalogue/topics/%00/reference-materials",
    ):
        assert (await client.get(path, headers=staff)).status_code == 422, path

    nul = "long enough \x00 text"
    for method, path, body in (
        ("POST", "/catalogue/courses/", {**_course(ids["department"], "NUL102"), "title": nul}),
        ("POST", "/catalogue/courses/", {**_course(ids["department"], "NUL103"), "description": nul}),
        ("POST", "/catalogue/courses/", {**_course(ids["department"], "NUL104"), "department_id": nul}),
        ("PATCH", f"/catalogue/courses/{course_id}", {"title": nul}),
        ("POST", f"/catalogue/courses/{course_id}/topics", {"title": nul, "slug": "nul", "sequence": 2}),
        ("POST", f"/catalogue/courses/{course_id}/topics", {"title": "Huge", "slug": "huge", "sequence": 10**30}),
        ("POST", f"/catalogue/topics/{topic_id}/learning-outcomes", {"sequence": 7, "description": nul}),
        ("POST", f"/catalogue/topics/{topic_id}/learning-outcomes", {"sequence": 2147483648, "description": "Long enough text"}),
        ("POST", f"/catalogue/topics/{topic_id}/reference-materials", {"title": "Hand\x00book", "material_type": "book"}),
        (
            "POST",
            f"/catalogue/topics/{topic_id}/reference-materials",
            {"title": "Handbook", "material_type": "book", "url": "https://example.com/" + "a" * 1024},
        ),
    ):
        response = await client.request(method, path, headers=staff, json=body)
        assert response.status_code == 422, (path, body, response.text)


async def test_values_at_the_edge_of_what_each_column_holds_are_stored(client):
    staff, ids = await institution(client, "admin")
    course = {
        **_course(ids["department"], "A" * 20, "s" * 80),
        "title": "T" * 200,
        "description": "d" * 100000,
    }
    created = await client.post("/catalogue/courses/", headers=staff, json=course)
    assert created.status_code == 201, created.text
    course_id = created.json()["data"]["id"]

    topic = await client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=staff,
        json={"title": "T" * 200, "slug": "s" * 80, "sequence": 2147483647},
    )
    assert topic.status_code == 201, topic.text

    material = await client.post(
        f"/catalogue/topics/{topic.json()['data']['id']}/reference-materials",
        headers=staff,
        json={"title": "T" * 200, "material_type": "book", "url": "https://example.com/" + "a" * (1024 - 20)},
    )
    assert material.status_code == 201, material.text

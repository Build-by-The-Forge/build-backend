"""The request is well formed but the catalogue's state refuses it. All of these answered 500."""

from uuid import uuid4

import pytest

from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


async def staff_context(client) -> tuple[dict, str, str]:
    _, slug, department_id, course_id, token = await seed_course_context(client, "admin")
    return headers(token, slug), department_id, course_id


def add_topic(client, staff: dict, course_id: str, sequence: int = 1):
    return client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=staff,
        json={"title": "Limits", "slug": f"limits-{uuid4().hex[:6]}", "sequence": sequence},
    )


def assert_conflict(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_archiving_anything_twice_is_a_conflict(client):
    staff, _, course_id = await staff_context(client)
    topic_id = add_topic(client, staff, course_id).json()["data"]["id"]
    outcome = client.post(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=staff,
        json={"sequence": 1, "description": "Explains what a limit is"},
    )
    material = client.post(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=staff,
        json={"title": "Handbook", "material_type": "book", "url": "https://example.com/handbook"},
    )

    for path in (
        f"/catalogue/learning-outcomes/{outcome.json()['data']['id']}",
        f"/catalogue/reference-materials/{material.json()['data']['id']}",
        f"/catalogue/topics/{topic_id}",
        f"/catalogue/courses/{course_id}",
    ):
        assert client.post(f"{path}/archive", headers=staff).status_code == 200, path
        assert_conflict(client.post(f"{path}/archive", headers=staff))


@pytest.mark.asyncio
async def test_a_taken_course_code_or_slug_is_a_conflict(client):
    staff, department_id, _ = await staff_context(client)

    def course(code: str, slug: str):
        return client.post(
            "/catalogue/courses/",
            headers=staff,
            json={
                "department_id": department_id,
                "code": code,
                "title": "Calculus One",
                "slug": slug,
                "credit_units": 3,
                "level": 100,
                "semester": 1,
            },
        )

    assert course("MTH101", "calculus-one").status_code == 201
    assert_conflict(course("MTH101", "calculus-two"))
    assert_conflict(course("MTH102", "calculus-one"))


@pytest.mark.asyncio
async def test_a_taken_topic_sequence_is_a_conflict_and_the_catalogue_still_works(client):
    staff, _, course_id = await staff_context(client)
    assert add_topic(client, staff, course_id, 1).status_code == 201

    assert_conflict(add_topic(client, staff, course_id, 1))

    assert add_topic(client, staff, course_id, 2).status_code == 201


@pytest.mark.asyncio
async def test_nothing_new_joins_something_archived_until_its_restored(client):
    staff, _, course_id = await staff_context(client)
    topic_id = add_topic(client, staff, course_id).json()["data"]["id"]
    outcome = {"sequence": 1, "description": "Explains what a limit is"}
    material = {"title": "Handbook", "material_type": "book", "url": "https://example.com/handbook"}

    def new_outcome():
        return client.post(f"/catalogue/topics/{topic_id}/learning-outcomes", headers=staff, json=outcome)

    def new_material():
        return client.post(f"/catalogue/topics/{topic_id}/reference-materials", headers=staff, json=material)

    assert client.post(f"/catalogue/topics/{topic_id}/archive", headers=staff).status_code == 200
    assert_conflict(new_outcome())
    assert_conflict(new_material())
    assert add_topic(client, staff, course_id, 2).status_code == 201, "the course itself is still open"

    assert client.post(f"/catalogue/courses/{course_id}/archive", headers=staff).status_code == 200
    assert_conflict(add_topic(client, staff, course_id, 3))

    assert client.post(f"/catalogue/courses/{course_id}/publish", headers=staff).status_code == 200
    assert add_topic(client, staff, course_id, 3).status_code == 201


@pytest.mark.asyncio
async def test_an_archived_course_refuses_children_of_its_active_topic_too(client):
    staff, _, course_id = await staff_context(client)
    topic_id = add_topic(client, staff, course_id).json()["data"]["id"]
    assert client.post(f"/catalogue/courses/{course_id}/archive", headers=staff).status_code == 200

    assert_conflict(
        client.post(
            f"/catalogue/topics/{topic_id}/learning-outcomes",
            headers=staff,
            json={"sequence": 1, "description": "Explains what a limit is"},
        )
    )
    assert_conflict(
        client.post(
            f"/catalogue/topics/{topic_id}/reference-materials",
            headers=staff,
            json={"title": "Handbook", "material_type": "book", "url": "https://example.com/handbook"},
        )
    )

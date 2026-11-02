"""What a reader sees of the catalogue: only what's active, at every level. A list holds
only what's active for staff too, as the contract says, until they ask for the rest. They
can still open what they archived, or they couldn't restore or audit it."""

from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import add_membership
from tests.integration.assessment.test_question_api import register_and_authenticate
from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


async def catalogue(client):
    tenant_id, slug, _, course_id, staff_token = await seed_course_context(client, "admin")
    staff = headers(staff_token, slug)
    student_id, student_token = await register_and_authenticate(client, f"reader-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    student = headers(student_token, slug)

    def add_topic(title: str, sequence: int = 1) -> str:
        created = client.post(
            f"/catalogue/courses/{course_id}/topics",
            headers=staff,
            json={"title": title, "slug": f"{title.lower().replace(' ', '-')}-{uuid4().hex[:6]}", "sequence": sequence},
        )
        assert created.status_code == 201, created.text
        return created.json()["data"]["id"]

    return course_id, staff, student, add_topic


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["data"]]


async def add_outcome(client, topic_id: str, staff: dict, sequence: int = 1) -> str:
    created = client.post(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=staff,
        json={"sequence": sequence, "description": f"Understands outcome number {sequence}"},
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


async def add_material(client, topic_id: str, staff: dict, title: str = "Handbook") -> str:
    created = client.post(
        f"/catalogue/topics/{topic_id}/reference-materials",
        headers=staff,
        json={"title": title, "material_type": "book", "url": "https://example.com/handbook"},
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def archive(client, path: str, staff: dict) -> None:
    archived = client.post(f"{path}/archive", headers=staff)
    assert archived.status_code == 200, archived.text


@pytest.mark.asyncio
async def test_a_reader_cant_find_an_archived_course_anywhere(client):
    course_id, staff, student, add_topic = await catalogue(client)
    topic_id = add_topic("Limits")
    assert client.get(f"/catalogue/courses/{course_id}", headers=student).status_code == 200
    assert course_id in ids(client.get("/catalogue/courses/", headers=student))

    archive(client, f"/catalogue/courses/{course_id}", staff)

    assert course_id not in ids(client.get("/catalogue/courses/", headers=student))
    for path in (
        f"/catalogue/courses/{course_id}",
        f"/catalogue/courses/{course_id}/topics",
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        f"/catalogue/topics/{topic_id}/reference-materials",
    ):
        refused = client.get(path, headers=student)
        assert refused.status_code == 404, path
        assert refused.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_staff_see_what_they_archived_only_when_they_ask(client):
    course_id, staff, _, add_topic = await catalogue(client)
    topic_id = add_topic("Limits")
    archive(client, f"/catalogue/topics/{topic_id}", staff)
    archive(client, f"/catalogue/courses/{course_id}", staff)

    assert course_id not in ids(client.get("/catalogue/courses/", headers=staff))
    assert course_id in ids(client.get("/catalogue/courses/?include_archived=true", headers=staff))
    assert client.get(f"/catalogue/courses/{course_id}", headers=staff).json()["data"]["status"] == "archived"
    assert topic_id not in ids(client.get(f"/catalogue/courses/{course_id}/topics", headers=staff))
    assert topic_id in ids(client.get(f"/catalogue/courses/{course_id}/topics?include_archived=true", headers=staff))


@pytest.mark.asyncio
async def test_a_reader_asking_for_whats_archived_is_refused(client):
    course_id, staff, student, add_topic = await catalogue(client)
    topic_id = add_topic("Limits")

    for path in (
        "/catalogue/courses/",
        f"/catalogue/courses/{course_id}/topics",
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        f"/catalogue/topics/{topic_id}/reference-materials",
    ):
        refused = client.get(f"{path}?include_archived=true", headers=student)
        assert refused.status_code == 403, path
        assert client.get(f"{path}?include_archived=true", headers=staff).status_code == 200, path


@pytest.mark.asyncio
async def test_a_reader_doesnt_see_an_archived_topic_or_what_hangs_from_it(client):
    course_id, staff, student, add_topic = await catalogue(client)
    kept, archived = add_topic("Kept", 1), add_topic("Archived", 2)
    archive(client, f"/catalogue/topics/{archived}", staff)

    assert ids(client.get(f"/catalogue/courses/{course_id}/topics", headers=student)) == [kept]
    assert client.get(f"/catalogue/topics/{archived}/learning-outcomes", headers=student).status_code == 404
    assert client.get(f"/catalogue/topics/{archived}/reference-materials", headers=student).status_code == 404


@pytest.mark.asyncio
async def test_a_reader_doesnt_see_an_archived_outcome(client):
    _, staff, student, add_topic = await catalogue(client)
    topic_id = add_topic("Limits")
    kept = await add_outcome(client, topic_id, staff, 1)
    archived = await add_outcome(client, topic_id, staff, 2)
    archive(client, f"/catalogue/learning-outcomes/{archived}", staff)

    assert ids(client.get(f"/catalogue/topics/{topic_id}/learning-outcomes", headers=student)) == [kept]
    assert ids(client.get(f"/catalogue/topics/{topic_id}/learning-outcomes", headers=staff)) == [kept]
    path = f"/catalogue/topics/{topic_id}/learning-outcomes?include_archived=true"
    assert set(ids(client.get(path, headers=staff))) == {kept, archived}


@pytest.mark.asyncio
async def test_a_reader_doesnt_see_an_archived_reference_material(client):
    _, staff, student, add_topic = await catalogue(client)
    topic_id = add_topic("Limits")
    kept = await add_material(client, topic_id, staff, "Kept")
    archived = await add_material(client, topic_id, staff, "Archived")
    archive(client, f"/catalogue/reference-materials/{archived}", staff)

    assert ids(client.get(f"/catalogue/topics/{topic_id}/reference-materials", headers=student)) == [kept]
    assert ids(client.get(f"/catalogue/topics/{topic_id}/reference-materials", headers=staff)) == [kept]
    path = f"/catalogue/topics/{topic_id}/reference-materials?include_archived=true"
    assert set(ids(client.get(path, headers=staff))) == {kept, archived}

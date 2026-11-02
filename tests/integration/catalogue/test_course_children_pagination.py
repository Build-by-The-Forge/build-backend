"""Topics, outcomes and reference materials against the contract: order and pages."""

from uuid import uuid4

import pytest

from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


async def course_with_children(client):
    _, slug, _, course_id, token = await seed_course_context(client, "admin")
    staff = headers(token, slug)

    def topic(sequence: int) -> str:
        created = client.post(
            f"/catalogue/courses/{course_id}/topics",
            headers=staff,
            json={"title": f"Topic {sequence}", "slug": f"topic-{uuid4().hex[:6]}", "sequence": sequence},
        )
        assert created.status_code == 201, created.text
        return created.json()["data"]["id"]

    topic_ids = {sequence: topic(sequence) for sequence in (3, 1, 2)}
    first = topic_ids[1]
    for sequence in (3, 1, 2):
        created = client.post(
            f"/catalogue/topics/{first}/learning-outcomes",
            headers=staff,
            json={"sequence": sequence, "description": f"Understands outcome number {sequence}"},
        )
        assert created.status_code == 201, created.text
    for title in ("Zeta", "Alpha", "Middle"):
        created = client.post(
            f"/catalogue/topics/{first}/reference-materials",
            headers=staff,
            json={"title": title, "material_type": "book", "url": "https://example.com/handbook"},
        )
        assert created.status_code == 201, created.text
    return staff, course_id, first


def page_of(client, path: str, staff: dict, key: str, limit: int, offset: int):
    response = client.get(f"{path}?limit={limit}&offset={offset}", headers=staff)
    assert response.status_code == 200, response.text
    return [item[key] for item in response.json()["data"]], response.json()["meta"]["pagination"]


@pytest.mark.asyncio
async def test_each_list_pages_in_its_contract_order(client):
    staff, course_id, topic_id = await course_with_children(client)

    for path, key, expected in (
        (f"/catalogue/courses/{course_id}/topics", "sequence", [1, 2, 3]),
        (f"/catalogue/topics/{topic_id}/learning-outcomes", "sequence", [1, 2, 3]),
        (f"/catalogue/topics/{topic_id}/reference-materials", "title", ["Alpha", "Middle", "Zeta"]),
    ):
        first, first_meta = page_of(client, path, staff, key, 2, 0)
        second, second_meta = page_of(client, path, staff, key, 2, 2)
        assert first + second == expected, path
        assert first_meta == {"total": 3, "limit": 2, "offset": 0}, path
        assert second_meta == {"total": 3, "limit": 2, "offset": 2}, path


@pytest.mark.asyncio
async def test_each_list_has_an_empty_page_past_its_end_and_refuses_a_bad_limit(client):
    staff, course_id, topic_id = await course_with_children(client)

    for path in (
        f"/catalogue/courses/{course_id}/topics",
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        f"/catalogue/topics/{topic_id}/reference-materials",
    ):
        past = client.get(f"{path}?offset=3", headers=staff)
        assert past.status_code == 200, path
        assert past.json()["data"] == [], path
        assert past.json()["meta"]["pagination"] == {"total": 3, "limit": 50, "offset": 3}, path
        assert client.get(f"{path}?limit=0", headers=staff).status_code == 422, path
        assert client.get(f"{path}?limit=101", headers=staff).status_code == 422, path
        assert client.get(f"{path}?offset=-1", headers=staff).status_code == 422, path


@pytest.mark.asyncio
async def test_a_child_list_of_something_missing_is_a_404_not_an_empty_page(client):
    staff, _, _ = await course_with_children(client)

    for path in (
        f"/catalogue/courses/{uuid4()}/topics",
        f"/catalogue/topics/{uuid4()}/learning-outcomes",
        f"/catalogue/topics/{uuid4()}/reference-materials",
    ):
        assert client.get(path, headers=staff).status_code == 404, path

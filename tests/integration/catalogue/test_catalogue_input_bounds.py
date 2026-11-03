"""Input PostgreSQL can't store or compare is refused here, the same on every database. On
PostgreSQL each of these answered 500, so pg_smoke repeats them there."""

import pytest

from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context

NUL = "a\x00b"


async def context(client):
    _, slug, department_id, course_id, token = await seed_course_context(client, "admin")
    staff = headers(token, slug)
    topic = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=staff,
        json={"title": "Limits", "slug": "limits", "sequence": 1},
    )
    assert topic.status_code == 201, topic.text
    return staff, department_id, course_id, topic.json()["data"]["id"]


def assert_refused(response) -> None:
    assert response.status_code == 422, (response.request.url.path, response.text)
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/catalogue/courses?department_id=%00",
        "/catalogue/departments?faculty_id=%00",
        "/catalogue/programmes?department_id=%00",
        "/catalogue/courses/%00",
        "/catalogue/courses/%00/topics",
        "/catalogue/topics/%00/learning-outcomes",
        "/catalogue/topics/%00/reference-materials",
    ],
)
async def test_a_nul_in_a_filter_or_an_id_is_refused(client, path):
    staff, _, _, _ = await context(client)

    assert_refused(client.get(path, headers=staff))


@pytest.mark.asyncio
async def test_a_nul_in_anything_written_is_refused(client):
    staff, department_id, course_id, topic_id = await context(client)
    course = {
        "department_id": department_id,
        "code": "MTH101",
        "title": "Calculus One",
        "slug": "calculus-one",
        "credit_units": 3,
        "level": 100,
        "semester": 1,
    }
    for field in ("department_id", "code", "title", "slug", "description"):
        assert_refused(client.post("/catalogue/courses/", headers=staff, json={**course, field: f"long enough {NUL}"}))
    for field in ("title", "description"):
        assert_refused(client.patch(f"/catalogue/courses/{course_id}", headers=staff, json={field: f"long enough {NUL}"}))
        assert_refused(client.patch(f"/catalogue/topics/{topic_id}", headers=staff, json={field: f"long enough {NUL}"}))
    for field in ("title", "slug", "description"):
        topic = {"title": "Series", "slug": "series", "sequence": 2, field: f"long enough {NUL}"}
        assert_refused(client.post(f"/catalogue/courses/{course_id}/topics", headers=staff, json=topic))
    outcome = {"sequence": 1, "description": f"long enough {NUL}"}
    assert_refused(client.post(f"/catalogue/topics/{topic_id}/learning-outcomes", headers=staff, json=outcome))
    for field in ("title", "url"):
        material = {"title": "Handbook", "material_type": "book", "url": "https://example.com/a", field: f"https://{NUL}"}
        assert_refused(client.post(f"/catalogue/topics/{topic_id}/reference-materials", headers=staff, json=material))


@pytest.mark.asyncio
@pytest.mark.parametrize("sequence", [2_147_483_648, 10**30, -(10**30)])
async def test_a_sequence_outside_its_column_is_refused(client, sequence):
    staff, _, course_id, topic_id = await context(client)

    topic = {"title": "Series", "slug": "series", "sequence": sequence}
    outcome = {"sequence": sequence, "description": "Explains what a limit is"}
    assert_refused(client.post(f"/catalogue/courses/{course_id}/topics", headers=staff, json=topic))
    assert_refused(client.post(f"/catalogue/topics/{topic_id}/learning-outcomes", headers=staff, json=outcome))


@pytest.mark.asyncio
async def test_the_largest_sequence_is_accepted(client):
    staff, _, course_id, _ = await context(client)

    topic = {"title": "Series", "slug": "series", "sequence": 2_147_483_647}
    assert client.post(f"/catalogue/courses/{course_id}/topics", headers=staff, json=topic).status_code == 201


@pytest.mark.asyncio
async def test_a_url_longer_than_its_column_is_refused(client):
    staff, _, _, topic_id = await context(client)
    material = {"title": "Handbook", "material_type": "book"}

    too_long = {**material, "url": "https://example.com/" + "a" * 1024}
    fits = {**material, "url": "https://example.com/" + "a" * (1024 - 20)}
    assert_refused(client.post(f"/catalogue/topics/{topic_id}/reference-materials", headers=staff, json=too_long))
    assert client.post(f"/catalogue/topics/{topic_id}/reference-materials", headers=staff, json=fits).status_code == 201

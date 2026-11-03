"""A domain rule refusing what a client wrote is the caller's to fix. The same error from
anywhere else is a server failure, and has to stay one."""

from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.domain.client_safe import ClientSafeError
from app.infrastructure.db.models.catalogue import CourseModel
from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


async def staff_and_topic(client) -> tuple[dict, str, str]:
    _, slug, _, course_id, token = await seed_course_context(client, "admin")
    staff = headers(token, slug)
    topic = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=staff,
        json={"title": "Limits", "slug": f"limits-{uuid4().hex[:6]}"},
    )
    assert topic.status_code == 201, topic.text
    return staff, course_id, topic.json()["data"]["id"]


def assert_refused(response, message: str) -> None:
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["message"] == message


@pytest.mark.asyncio
async def test_a_rule_refusing_a_new_outcome_answers_422_with_its_message(client):
    # This answered 500: the description's length is the domain's rule, not the schema's.
    staff, _, topic_id = await staff_and_topic(client)

    response = client.post(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=staff,
        json={"sequence": 1, "description": "short"},
    )

    assert_refused(response, "learning outcome description must be 10-1000 chars")


@pytest.mark.asyncio
async def test_a_rule_refusing_an_edited_outcome_answers_422_too(client):
    staff, _, topic_id = await staff_and_topic(client)
    outcome = client.post(
        f"/catalogue/topics/{topic_id}/learning-outcomes",
        headers=staff,
        json={"sequence": 1, "description": "Explains what a limit is"},
    )
    assert outcome.status_code == 201, outcome.text

    response = client.patch(
        f"/catalogue/learning-outcomes/{outcome.json()['data']['id']}",
        headers=staff,
        json={"description": "short"},
    )

    assert_refused(response, "learning outcome description must be 10-1000 chars")


@pytest.mark.asyncio
async def test_a_marked_error_on_a_read_is_a_server_failure_not_the_callers(client, monkeypatch):
    # What a stored row that no longer satisfies a rule looks like: the reader did nothing wrong.
    from app.api.catalogue import courses

    _, slug, _, _, token = await seed_course_context(client, "admin")

    async def broken(**_):
        raise ClientSafeError("course title must be 3-200 chars")

    monkeypatch.setattr(courses.service, "list_courses", broken)
    response = client.get("/catalogue/courses/", headers=headers(token, slug))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "course title" not in response.text


@pytest.mark.asyncio
async def test_a_missing_repository_is_a_wiring_fault_not_a_refusal():
    from app.application.catalogue.course_service import CourseService

    with pytest.raises(RuntimeError, match="repository is required"):
        await CourseService().list_courses(tenant_id="tenant")


async def break_stored_title(course_id: str) -> None:
    async with SessionLocal() as session:
        course = await session.get(CourseModel, course_id)
        course.title = "x"
        await session.commit()


@pytest.mark.asyncio
async def test_a_stored_row_breaking_a_rule_is_a_server_failure_on_every_route(client):
    # The client's own input is fine on all of these: only what's stored is wrong.
    staff, course_id, topic_id = await staff_and_topic(client)
    await break_stored_title(course_id)

    outcome = {"sequence": 1, "description": "Explains what a limit is"}
    material = {"title": "Handbook", "material_type": "book", "url": "https://example.com/handbook"}
    topic = {"title": "Series", "slug": "series", "sequence": 2}
    for response in (
        client.get(f"/catalogue/courses/{course_id}", headers=staff),
        client.get("/catalogue/courses", headers=staff),
        client.get(f"/catalogue/courses/{course_id}/topics", headers=staff),
        client.patch(f"/catalogue/courses/{course_id}", headers=staff, json={"description": "Fine"}),
        client.post(f"/catalogue/courses/{course_id}/topics", headers=staff, json=topic),
        client.patch(f"/catalogue/topics/{topic_id}", headers=staff, json={"description": "Fine text"}),
        client.post(f"/catalogue/topics/{topic_id}/learning-outcomes", headers=staff, json=outcome),
        client.post(f"/catalogue/topics/{topic_id}/reference-materials", headers=staff, json=material),
        client.post(f"/catalogue/topics/{topic_id}/archive", headers=staff),
        client.post(f"/catalogue/courses/{course_id}/archive", headers=staff),
    ):
        assert response.status_code == 500, (response.request.method, response.request.url.path, response.text)
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "title" not in response.json()["error"]["message"]

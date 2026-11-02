"""A domain rule refusing what a client wrote is the caller's to fix. The same error from
anywhere else is a server failure, and has to stay one."""

from uuid import uuid4

import pytest

from app.domain.client_safe import ClientSafeError
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
        await CourseService().list_courses()

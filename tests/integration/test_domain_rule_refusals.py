"""A domain rule refusing a request is the caller's to fix, not a server failure."""

from uuid import uuid4

import pytest

from tests.integration.catalogue.test_tenant_scoped_mutations import headers, seed_course_context


@pytest.mark.asyncio
async def test_a_rule_a_route_doesnt_catch_answers_422_with_its_message(client):
    # This answered 500: the description's length is the domain's rule, not the schema's.
    _, slug, _, course_id, token = await seed_course_context(client, "admin")
    staff = headers(token, slug)
    topic = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=staff,
        json={"title": "Limits", "slug": f"limits-{uuid4().hex[:6]}"},
    )
    assert topic.status_code == 201, topic.text

    response = client.post(
        f"/catalogue/topics/{topic.json()['data']['id']}/learning-outcomes",
        headers=staff,
        json={"sequence": 1, "description": "short"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["message"] == "learning outcome description must be 10-1000 chars"


@pytest.mark.asyncio
async def test_a_failure_that_isnt_a_rule_still_answers_500_and_says_nothing(client, monkeypatch):
    from app.api.catalogue import courses

    _, slug, _, _, token = await seed_course_context(client, "admin")

    async def broken(**_):
        raise ValueError("internal detail, not written for clients")

    monkeypatch.setattr(courses.service, "list_courses", broken)
    response = client.get("/catalogue/courses/", headers=headers(token, slug))

    assert response.status_code == 500
    assert "internal detail" not in response.text

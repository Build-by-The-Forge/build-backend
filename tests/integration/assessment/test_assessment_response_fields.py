"""No mobile assessment response carries tenant_id or user_id (M3-E, G-39), and
removing them changes no authorization: another student's attempt is still a
404 on every attempt route."""

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import TenantModel
from tests.integration.assessment.test_attempt_api import add_membership, headers
from tests.integration.assessment.test_question_api import register_and_authenticate
from tests.integration.assessment.test_result_release_api import policy, published

INTERNAL = {"tenant_id", "user_id"}


def keys(value: Any) -> set[str]:
    """Every key at any depth."""
    if isinstance(value, dict):
        return set(value) | {k for item in value.values() for k in keys(item)}
    if isinstance(value, list):
        return {k for item in value for k in keys(item)}
    return set()


def ok(response) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    return response.json()


async def test_no_mobile_assessment_response_carries_tenant_or_user_ids(client):
    _, student, assessment_id = await published(client, policy(max_attempts=2))

    started = ok(client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student))
    attempt_id = started["data"]["id"]
    [question] = ok(client.get(f"/assessment/attempts/{attempt_id}/questions", headers=student))["data"]["questions"]
    ok(
        client.put(
            f"/assessment/attempts/{attempt_id}/answers/{question['assessment_question_id']}",
            json={"selected_option_index": 1},
            headers=student,
        )
    )
    responses = {
        "start": started,
        "submit": ok(client.post(f"/assessment/attempts/{attempt_id}/submit", headers=student)),
        "list assessments": ok(client.get("/assessment/assessments", headers=student)),
        "get assessment": ok(client.get(f"/assessment/assessments/{assessment_id}", headers=student)),
        "list attempts": ok(client.get("/assessment/attempts", headers=student)),
        "get attempt": ok(client.get(f"/assessment/attempts/{attempt_id}", headers=student)),
        "result": ok(client.get(f"/assessment/attempts/{attempt_id}/result", headers=student)),
    }

    leaks = {name: sorted(keys(body["data"]) & INTERNAL) for name, body in responses.items()}
    assert leaks == {name: [] for name in responses}
    # The fields that identify the attempt are still there.
    assert responses["get attempt"]["data"]["id"] == attempt_id
    assert responses["result"]["data"]["attempt_id"] == attempt_id


async def test_another_students_attempt_is_still_not_found_on_every_attempt_route(client):
    _, student, assessment_id = await published(client, policy(max_attempts=2))
    attempt_id = ok(client.post(f"/assessment/assessments/{assessment_id}/attempts", headers=student))["data"]["id"]
    tenant_slug = student["X-Tenant-Slug"]
    other_id, token = await register_and_authenticate(client, f"fields-other-{uuid4()}@example.com")
    async with SessionLocal() as session:
        tenant_id = await session.scalar(select(TenantModel.id).where(TenantModel.slug == tenant_slug))
    await add_membership(other_id, tenant_id, "student")
    other = headers(token, tenant_slug)

    attempts = [
        client.get(f"/assessment/attempts/{attempt_id}", headers=other),
        client.get(f"/assessment/attempts/{attempt_id}/questions", headers=other),
        client.post(f"/assessment/attempts/{attempt_id}/submit", headers=other),
        client.get(f"/assessment/attempts/{attempt_id}/result", headers=other),
    ]
    assert [response.status_code for response in attempts] == [404, 404, 404, 404]
    # And theirs isn't in the other student's list.
    assert attempt_id not in client.get("/assessment/attempts", headers=other).text
    # The owner's attempt is untouched by those requests.
    assert ok(client.get(f"/assessment/attempts/{attempt_id}", headers=student))["data"]["status"] == "in_progress"

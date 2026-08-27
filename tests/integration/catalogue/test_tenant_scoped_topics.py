from uuid import uuid4

import pytest
from tests.integration.catalogue.test_tenant_scoped_mutations import (
    headers,
    seed_course_context,
)


@pytest.mark.asyncio
async def test_topic_creation_requires_authentication(client):
    response = client.post(
        "/catalogue/courses/course-id/topics",
        json={"title": "Topic Title", "slug": "topic-title"},
    )

    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_student_cannot_create_topic(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "student")

    response = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=headers(token, tenant_slug),
        json={"title": "Topic Title", "slug": "topic-title"},
    )

    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_lecturer_creates_and_reads_topics_in_own_tenant(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client)
    request_headers = headers(token, tenant_slug)

    created = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=request_headers,
        json={
            "title": "Linear Regression",
            "slug": "linear-regression",
            "description": "Introduction to linear regression.",
            "sequence": 2,
        },
    )

    assert created.status_code == 201
    topic = created.json()["data"]
    assert topic["course_id"] == course_id
    assert topic["sequence"] == 2

    listed = client.get(
        f"/catalogue/courses/{course_id}/topics", headers=request_headers
    )
    assert listed.status_code == 200
    assert listed.json()["data"] == [topic]


@pytest.mark.asyncio
async def test_topic_creation_rejects_client_tenant_id(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client)

    response = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=headers(token, tenant_slug),
        json={
            "title": "Injected Topic",
            "slug": "injected-topic",
            "tenant_id": str(uuid4()),
        },
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_topic_creation_cannot_cross_tenant_course(client):
    _, tenant_a_slug, _, course_a_id, token_a = await seed_course_context(client)
    _, tenant_b_slug, _, course_b_id, _ = await seed_course_context(client)

    response = client.post(
        f"/catalogue/courses/{course_b_id}/topics",
        headers=headers(token_a, tenant_a_slug),
        json={"title": "Cross Tenant Topic", "slug": "cross-tenant-topic"},
    )

    assert response.status_code == 404
    assert response.json()["success"] is False
    assert course_a_id != course_b_id
    assert tenant_a_slug != tenant_b_slug


@pytest.mark.asyncio
async def test_topics_for_missing_course_return_not_found(client):
    _, tenant_slug, _, _, token = await seed_course_context(client)

    response = client.get(
        f"/catalogue/courses/{uuid4()}/topics",
        headers=headers(token, tenant_slug),
    )

    assert response.status_code == 404
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_lecturer_updates_and_archives_topic(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(
        client, "faculty_admin"
    )
    request_headers = headers(token, tenant_slug)
    created = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=request_headers,
        json={"title": "Topic To Update", "slug": "topic-to-update"},
    )
    topic_id = created.json()["data"]["id"]

    updated = client.patch(
        f"/catalogue/topics/{topic_id}",
        headers=request_headers,
        json={"title": "Updated Topic"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "Updated Topic"

    archived = client.post(
        f"/catalogue/topics/{topic_id}/archive", headers=request_headers
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"


@pytest.mark.asyncio
async def test_student_cannot_create_topic_without_permission(client):
    _, tenant_slug, _, course_id, token = await seed_course_context(client, "student")
    request_headers = headers(token, tenant_slug)
    response = client.post(
        f"/catalogue/courses/{course_id}/topics",
        headers=request_headers,
        json={"title": "Student Topic", "slug": "student-topic"},
    )
    assert response.status_code == 403
    assert response.json()["success"] is False

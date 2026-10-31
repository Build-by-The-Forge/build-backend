"""A student never receives storage locations, identities or processing
internals from any content read route. Staff keep what their work needs."""

from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.uploads import upload_asset

STAFF_ONLY = {
    "storage_uri",
    "created_by",
    "created_by_email",
    "tenant_id",
    "metadata",
    "trust_policy",
    "correlation_id",
    "external_task_id",
    "attempt_history",
    "error_details",
    "metrics",
    "last_dispatched_at",
    "last_callback_at",
}


def field_names(node) -> set[str]:
    if isinstance(node, dict):
        return set(node).union(*(field_names(value) for value in node.values())) if node else set()
    if isinstance(node, list):
        return set().union(*(field_names(item) for item in node)) if node else set()
    return set()


async def content(client):
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"fields-lecturer-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(lecturer_id, "lecturer")
    lecturer = headers(lecturer_token, slug)
    source = client.post(
        "/content/sources",
        json={
            "code": f"SRC_F_{uuid4().hex[:6].upper()}",
            "name": "Fields",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=lecturer,
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["data"]["id"]
    asset = upload_asset(client, source_id, headers=lecturer, name="notes.pdf")
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["data"]["id"]
    job = client.post(f"/content/assets/{asset_id}/jobs", json={"max_attempts": 3}, headers=lecturer)
    assert job.status_code == 201, job.text
    student_id, student_token = await register_and_authenticate(client, f"fields-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    return lecturer, headers(student_token, slug), source_id, asset_id, job.json()["data"]["id"]


def read_routes(source_id: str, asset_id: str, job_id: str) -> list[str]:
    return [
        "/content/sources",
        f"/content/sources/{source_id}",
        f"/content/sources/{source_id}/assets",
        "/content/assets",
        f"/content/assets/{asset_id}",
        f"/content/assets/{asset_id}/jobs",
        f"/content/assets/{asset_id}/jobs/latest",
        "/content/jobs",
        f"/content/jobs/{job_id}",
    ]


@pytest.mark.asyncio
async def test_no_content_read_route_gives_a_student_an_internal_field(client):
    _, student, source_id, asset_id, job_id = await content(client)
    for path in read_routes(source_id, asset_id, job_id):
        response = client.get(path, headers=student)
        assert response.status_code == 200, f"{path}: {response.text}"
        assert not field_names(response.json()) & STAFF_ONLY, path
        assert "s3://" not in response.text, path
        assert "@build.internal" not in response.text, path


@pytest.mark.asyncio
async def test_a_student_still_gets_what_the_app_needs(client):
    _, student, _, asset_id, job_id = await content(client)
    asset = client.get(f"/content/assets/{asset_id}", headers=student).json()["data"]
    assert {"id", "source_id", "file_name", "mime_type", "ingestion_status"} <= set(asset)
    job = client.get(f"/content/jobs/{job_id}", headers=student).json()["data"]
    assert {"id", "asset_id", "status", "is_retryable"} <= set(job)


@pytest.mark.asyncio
async def test_staff_keep_the_internal_fields(client):
    lecturer, _, source_id, asset_id, job_id = await content(client)
    asset = client.get(f"/content/assets/{asset_id}", headers=lecturer).json()["data"]
    assert asset["storage_uri"]
    assert asset["created_by_email"]
    source = client.get(f"/content/sources/{source_id}", headers=lecturer).json()["data"]
    assert "trust_policy" in source
    job = client.get(f"/content/jobs/{job_id}", headers=lecturer).json()["data"]
    assert "attempt_history" in job


@pytest.mark.asyncio
async def test_tenant_isolation_is_unchanged(client):
    _, _, source_id, asset_id, job_id = await content(client)
    other_lecturer, other_student, _, _, _ = await content(client)
    for reader in (other_student, other_lecturer):
        assert client.get(f"/content/assets/{asset_id}", headers=reader).status_code == 404
        assert client.get(f"/content/jobs/{job_id}", headers=reader).status_code == 404
        assert client.get(f"/content/sources/{source_id}", headers=reader).status_code == 404

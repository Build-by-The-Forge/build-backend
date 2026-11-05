"""The read policy over HTTP (M3-D PR 4): what a student and staff reach on
the existing content routes, and that a refusal looks exactly like a missing
document."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.infrastructure.db.models.content import ContentAssetModel, ContentRightsAssertionModel
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.uploads import upload_asset


async def tenant_with_document(client):
    admin_id, admin_token = await register_and_authenticate(client, f"policy-admin-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    admin = headers(admin_token, slug)
    student_id, student_token = await register_and_authenticate(client, f"policy-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_id, "student")
    student = headers(student_token, slug)
    source = client.post(
        "/content/sources",
        json={
            "code": f"SRC_POL_{uuid4().hex[:6].upper()}",
            "name": "Policy",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
        headers=admin,
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["data"]["id"]
    uploaded = upload_asset(client, source_id, headers=admin)
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["data"]["id"]
    job = client.post(f"/content/assets/{asset_id}/jobs", json={}, headers=admin)
    assert job.status_code == 201, job.text
    return admin, student, student_id, source_id, asset_id, job.json()["data"]["id"]


def student_reads(client, student, source_id, asset_id, job_id):
    return {
        "list": client.get("/content/assets", headers=student),
        "source list": client.get(f"/content/sources/{source_id}/assets", headers=student),
        "get": client.get(f"/content/assets/{asset_id}", headers=student),
        "job": client.get(f"/content/jobs/{job_id}", headers=student),
        "latest job": client.get(f"/content/assets/{asset_id}/jobs/latest", headers=student),
        "asset jobs": client.get(f"/content/assets/{asset_id}/jobs", headers=student),
        "jobs": client.get("/content/jobs", headers=student),
    }


@pytest.mark.asyncio
async def test_a_student_cant_reach_unclassified_staff_material_on_any_route(client):
    # Every staff upload is unclassified until reviewed: students see none of it.
    admin, student, _, source_id, asset_id, job_id = await tenant_with_document(client)

    reads = student_reads(client, student, source_id, asset_id, job_id)

    for name in ("list", "source list", "asset jobs", "jobs"):
        assert reads[name].status_code == 200, (name, reads[name].text)
        assert asset_id not in reads[name].text and job_id not in reads[name].text, name
    assert reads["list"].json()["meta"]["total"] == 0
    assert reads["jobs"].json()["meta"]["total"] == 0
    # A refusal is exactly a missing document's answer.
    missing = str(uuid4())
    assert (reads["get"].status_code, reads["get"].json()) == (
        client.get(f"/content/assets/{missing}", headers=student).status_code,
        client.get(f"/content/assets/{missing}", headers=student).json() | {"meta": reads["get"].json().get("meta")},
    )
    assert reads["job"].status_code == 404 and reads["latest job"].status_code == 404
    assert reads["job"].json() == client.get(f"/content/jobs/{missing}", headers=student).json()
    # Staff who manage shared material still reach it on the staff routes.
    assert client.get(f"/content/assets/{asset_id}", headers=admin).status_code == 200
    assert asset_id in client.get("/content/assets", headers=admin).text
    assert client.get(f"/content/jobs/{job_id}", headers=admin).status_code == 200


@pytest.mark.asyncio
async def test_staff_cant_reach_or_operate_on_a_students_personal_document(client):
    admin, _, student_id, source_id, asset_id, job_id = await tenant_with_document(client)
    # The document becomes the student's own (as their uploads will be, in PR 8).
    async with SessionLocal() as session:
        await session.execute(
            update(ContentAssetModel)
            .where(ContentAssetModel.id == asset_id)
            .values(ownership_class="personal", owner_user_id=student_id)
        )
        await session.commit()

    assert client.get(f"/content/assets/{asset_id}", headers=admin).status_code == 404
    assert asset_id not in client.get("/content/assets", headers=admin).text
    assert asset_id not in client.get(f"/content/sources/{source_id}/assets", headers=admin).text
    assert client.get(f"/content/jobs/{job_id}", headers=admin).status_code == 404
    assert job_id not in client.get("/content/jobs", headers=admin).text
    # Operating on it is refused the same way: as if it didn't exist.
    for response in (
        client.post(f"/content/assets/{asset_id}/jobs", json={}, headers=admin),
        client.post(f"/content/assets/{asset_id}/reprocess", json={}, headers=admin),
        client.post(f"/content/jobs/{job_id}/retry", json={"delay_seconds": 1}, headers=admin),
        client.post(f"/content/jobs/{job_id}/dispatch", headers=admin),
        client.post(f"/content/jobs/{job_id}/reconcile", headers=admin),
        client.post(f"/content/assets/{asset_id}/revoke", json={"reason": "x"}, headers=admin),
    ):
        assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_institutional_material_reviewed_for_the_tenant_is_readable_by_students(client):
    admin, student, student_id, source_id, asset_id, job_id = await tenant_with_document(client)
    async with SessionLocal() as session:
        await session.execute(
            update(ContentAssetModel).where(ContentAssetModel.id == asset_id).values(ownership_class="institutional")
        )
        tenant_id = (await session.get(ContentAssetModel, asset_id)).tenant_id
        session.add(
            ContentRightsAssertionModel(
                id=str(uuid4()),
                tenant_id=tenant_id,
                asset_id=asset_id,
                asserted_by=student_id,
                kind="staff_review",
                rights_basis="lecturer_provided",
                audience="tenant",
                redistribution="tenant_only",
                ai_use="not_permitted",
                outcome="accepted",
                reason="reviewed",
                asserted_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    reads = student_reads(client, student, source_id, asset_id, job_id)
    assert reads["get"].status_code == 200
    assert reads["job"].status_code == 200
    assert reads["list"].json()["meta"]["total"] == 1
    # The student's view still hides staff internals (G-06).
    assert "storage_uri" not in reads["get"].json()["data"]

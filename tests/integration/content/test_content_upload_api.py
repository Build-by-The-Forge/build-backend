"""POST /content/sources/{id}/assets/upload through the real app: auth,
permissions, tenancy and the HTTP contract. Storage is the in-memory fake
from test_content_upload_service; real storage is proven in the storage
gate."""

from uuid import uuid4

import pytest

from app.api.content import assets as assets_api
from app.core.authorization import Permission
from app.domain.content.storage import ObjectStorageConfigurationError, ObjectStorageUnavailableError
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.test_content_upload_service import FakeStorage

PDF_HEAD = b"%PDF-1.7\n"


def pdf() -> bytes:
    """Unique bytes per call: duplicate content is tenant-wide."""
    return PDF_HEAD + uuid4().hex.encode() * 50


@pytest.fixture
def storage(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(assets_api.upload_service, "_storage_factory", lambda: fake)
    return fake


@pytest.fixture
async def tenant_a(client):
    admin_id, _ = await register_and_authenticate(client, f"upload-admin-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    lecturer_id, lecturer_token = await register_and_authenticate(client, f"upload-lecturer-{uuid4()}@example.com")
    await add_membership(lecturer_id, tenant_id, "lecturer")
    lecturer = headers(lecturer_token, slug)
    source = client.post(
        "/content/sources",
        headers=lecturer,
        json={
            "code": f"UPL_{uuid4().hex[:8].upper()}",
            "name": "MTS 102 notes",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert source.status_code == 201, source.text
    return {"id": tenant_id, "slug": slug, "lecturer": lecturer, "source_id": source.json()["data"]["id"]}


def upload(client, tenant, body, *, key="k-1", name="notes.pdf", hdrs=None, source_id=None):
    request_headers = dict(hdrs or tenant["lecturer"])
    if key is not None:
        request_headers["Idempotency-Key"] = key
    request_headers["Content-Type"] = "application/octet-stream"  # decides nothing
    return client.post(
        f"/content/sources/{source_id or tenant['source_id']}/assets/upload",
        params={"file_name": name},
        headers=request_headers,
        content=body,
    )


async def test_an_upload_creates_then_replays_the_asset(client, tenant_a, storage):
    body = pdf()

    created = upload(client, tenant_a, body, key="k-api")
    replayed = upload(client, tenant_a, body, key="k-api")

    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert (data["mime_type"], data["file_size_bytes"]) == ("application/pdf", len(body))
    assert data["storage_uri"].startswith(f"s3://{assets_api.settings.object_storage_bucket}/tenants/{tenant_a['id']}/assets/")
    assert replayed.status_code == 200
    assert replayed.json()["data"]["id"] == data["id"]
    assert storage.puts == 1


async def test_key_reuse_and_duplicate_content_are_distinct_409s(client, tenant_a, storage):
    body = pdf()
    first = upload(client, tenant_a, body, key="k-first").json()["data"]

    reused = upload(client, tenant_a, pdf(), key="k-first")
    duplicate = upload(client, tenant_a, body, key="k-second")

    assert (reused.status_code, reused.json()["error"]["code"]) == (409, "IDEMPOTENCY_KEY_REUSED")
    assert (duplicate.status_code, duplicate.json()["error"]["code"]) == (409, "DUPLICATE_CONTENT")
    # A lecturer may read assets, so the existing one is named.
    assert duplicate.json()["error"]["existing_asset_id"] == first["id"]


async def test_the_existing_asset_is_not_named_without_read_permission(client, tenant_a, storage, monkeypatch):
    body = pdf()
    upload(client, tenant_a, body, key="k-seen")
    real_can = assets_api.authorization.can
    monkeypatch.setattr(
        assets_api.authorization,
        "can",
        lambda context, permission: permission != Permission.CONTENT_ASSET_READ and real_can(context, permission),
    )

    duplicate = upload(client, tenant_a, body, key="k-unseen")

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_CONTENT"
    assert "existing_asset_id" not in duplicate.json()["error"]


async def test_a_student_cannot_upload(client, tenant_a, storage):
    student_id, student_token = await register_and_authenticate(client, f"upload-student-{uuid4()}@example.com")
    await add_membership(student_id, tenant_a["id"], "student")

    response = upload(client, tenant_a, pdf(), hdrs=headers(student_token, tenant_a["slug"]))

    assert response.status_code == 403
    assert storage.puts == 0


async def test_another_tenants_source_is_not_found(client, tenant_a, storage):
    other_id, other_token = await register_and_authenticate(client, f"upload-other-{uuid4()}@example.com")
    _, other_slug, _, _ = await seed_tenant_context(other_id, "lecturer")

    response = upload(client, tenant_a, pdf(), hdrs=headers(other_token, other_slug))
    missing = upload(client, tenant_a, pdf(), source_id=str(uuid4()))

    assert response.status_code == missing.status_code == 404
    assert response.json() == {"error": {"code": "SOURCE_NOT_FOUND", "message": "no such source"}}
    assert storage.puts == 0


@pytest.mark.parametrize(
    ("body", "key", "name", "status", "code"),
    [
        (b"%PDF-1.7 x", None, "a.pdf", 400, "INVALID_IDEMPOTENCY_KEY"),
        (b"%PDF-1.7 x", "k", "../a.pdf", 400, "INVALID_FILE_NAME"),
        (b"", "k", "a.pdf", 400, "EMPTY_UPLOAD"),
        (b"<html>", "k", "a.pdf", 415, "UNSUPPORTED_MEDIA_TYPE"),
        (b"%PDF-1.7 x", "k", "a.png", 415, "UNSUPPORTED_MEDIA_TYPE"),
    ],
)
async def test_invalid_uploads_are_refused_before_storage(client, tenant_a, storage, body, key, name, status, code):
    response = upload(client, tenant_a, body, key=key, name=name)

    assert (response.status_code, response.json()["error"]["code"]) == (status, code)
    assert storage.puts == 0


async def test_unavailable_storage_is_503_with_retry_after(client, tenant_a, storage):
    storage.put_error = ObjectStorageUnavailableError("down")

    response = upload(client, tenant_a, pdf(), key="k-down")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OBJECT_STORAGE_UNAVAILABLE"
    assert response.headers["Retry-After"] == "5"


async def test_unconfigured_storage_is_503_and_needed_only_to_store(client, tenant_a, monkeypatch):
    def unconfigured():
        raise ObjectStorageConfigurationError("no bucket")

    monkeypatch.setattr(assets_api.upload_service, "_storage_factory", unconfigured)

    refused = upload(client, tenant_a, b"<html>", key="k-early")
    response = upload(client, tenant_a, pdf(), key="k-unconfigured")

    assert refused.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OBJECT_STORAGE_NOT_CONFIGURED"

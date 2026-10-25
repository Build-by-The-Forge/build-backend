"""POST /content/assets/{id}/versions/upload through the real app (P3-1
PR 3b): the HTTP contract of the version transition."""

from uuid import uuid4

import pytest

from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.test_content_source_api import add_membership
from tests.integration.content.uploads import pdf_bytes, upload_asset


async def _lecturer(client) -> dict:
    admin_id, _ = await register_and_authenticate(client, f"ver-admin-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    user_id, token = await register_and_authenticate(client, f"ver-lecturer-{uuid4()}@example.com")
    await add_membership(user_id, tenant_id, "lecturer")
    h = headers(token, slug)
    source = client.post(
        "/content/sources",
        headers=h,
        json={
            "code": f"VER_{uuid4().hex[:8].upper()}",
            "name": "Versioned notes",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert source.status_code == 201, source.text
    return {"h": h, "source": source.json()["data"]["id"]}


def _version(client, asset_id, h, *, data=None, key="v-1", name="notes-v2.pdf"):
    request_headers = dict(h) | {"Idempotency-Key": key, "Content-Type": "application/octet-stream"}
    return client.post(
        f"/content/assets/{asset_id}/versions/upload",
        params={"file_name": name},
        headers=request_headers,
        content=data if data is not None else pdf_bytes(),
    )


@pytest.fixture
async def asset(client) -> dict:
    lecturer = await _lecturer(client)
    response = upload_asset(client, lecturer["source"], headers=lecturer["h"])
    assert response.status_code == 201, response.text
    return lecturer | {"asset": response.json()["data"]}


async def test_a_version_is_created_and_a_retry_returns_it(client, asset):
    data = pdf_bytes()

    created = _version(client, asset["asset"]["id"], asset["h"], data=data, key="v-api")
    retried = _version(client, asset["asset"]["id"], asset["h"], data=data, key="v-api")

    assert created.status_code == 201, created.text
    child = created.json()["data"]
    assert (child["parent_asset_id"], child["asset_version"], child["status"]) == (asset["asset"]["id"], 2, "active")
    assert retried.status_code == 200 and retried.json()["data"]["id"] == child["id"]
    parent = client.get(f"/content/assets/{asset['asset']['id']}", headers=asset["h"]).json()["data"]
    assert parent["status"] == "superseded"


async def test_a_superseded_asset_answers_409_conflict(client, asset):
    _version(client, asset["asset"]["id"], asset["h"], key="v-a")

    response = _version(client, asset["asset"]["id"], asset["h"], key="v-b")

    assert (response.status_code, response.json()["error"]["code"]) == (409, "ASSET_VERSION_CONFLICT")


async def test_duplicate_content_names_the_existing_asset(client, asset):
    data = pdf_bytes()
    other = upload_asset(client, asset["source"], headers=asset["h"], data=data).json()["data"]

    response = _version(client, asset["asset"]["id"], asset["h"], data=data, key="v-dup")

    assert (response.status_code, response.json()["error"]["code"]) == (409, "DUPLICATE_CONTENT")
    assert response.json()["error"]["existing_asset_id"] == other["id"]
    parent = client.get(f"/content/assets/{asset['asset']['id']}", headers=asset["h"]).json()["data"]
    assert parent["status"] == "active"


async def test_another_tenant_gets_404_and_nothing_changes(client, asset):
    other = await _lecturer(client)

    response = _version(client, asset["asset"]["id"], other["h"])
    missing = _version(client, str(uuid4()), other["h"])

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    parent = client.get(f"/content/assets/{asset['asset']['id']}", headers=asset["h"]).json()["data"]
    assert parent["status"] == "active"


async def test_a_version_body_over_the_upload_limit_is_413(client, asset, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 2048)

    response = _version(client, asset["asset"]["id"], asset["h"], data=b"%PDF-1.7\n" + b"x" * 4096)

    assert response.status_code == 413, response.text

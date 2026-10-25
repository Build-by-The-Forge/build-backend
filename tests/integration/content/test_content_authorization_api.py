"""P3-1 PR 3a regressions, through the real app: no tenant can change
another tenant's content, and no tenant can create or change platform
content. Each case was reproduced on main ea65510 before the fix. Every
test checks the state afterwards, not only the status code."""

import hashlib
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.domain.content.asset import ContentAsset
from app.infrastructure.content.unit_of_work import ContentUnitOfWork
from tests.integration.assessment.test_attempt_api import headers
from tests.integration.assessment.test_question_api import register_and_authenticate, seed_tenant_context
from tests.integration.content.test_content_source_api import add_membership, seed_platform_source

REASON = {"reason": "Regression check"}


def _sha() -> str:
    return hashlib.sha256(uuid4().bytes).hexdigest()


def _register_body(**overrides) -> dict:
    body = {
        "file_name": "notes.pdf",
        "mime_type": "application/pdf",
        "file_size_bytes": 5,
        "content_sha256": _sha(),
        "storage_uri": "s3://build-documents/x",
    }
    return body | overrides


def _version_body() -> dict:
    return _register_body(file_name="v2.pdf", storage_uri="s3://attacker/v2.pdf")


async def _tenant(client, role: str = "lecturer") -> dict:
    admin_id, _ = await register_and_authenticate(client, f"authz-admin-{uuid4()}@example.com")
    tenant_id, slug, _, _ = await seed_tenant_context(admin_id, "admin")
    user_id, token = await register_and_authenticate(client, f"authz-{role}-{uuid4()}@example.com")
    await add_membership(user_id, tenant_id, role)
    return {"id": tenant_id, "h": headers(token, slug)}


def _source(client, tenant) -> str:
    response = client.post(
        "/content/sources",
        headers=tenant["h"],
        json={
            "code": f"AZ_{uuid4().hex[:8].upper()}",
            "name": "Authorization notes",
            "source_type": "lecturer_upload",
            "authority_level": "institutional",
            "visibility": "tenant",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _asset(client, tenant, source_id) -> str:
    response = client.post(f"/content/sources/{source_id}/assets", headers=tenant["h"], json=_register_body())
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _asset_state(client, tenant, asset_id) -> dict:
    response = client.get(f"/content/assets/{asset_id}", headers=tenant["h"])
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _platform_asset(source_id: str) -> str:
    asset = ContentAsset.create(
        source_id=source_id,
        tenant_id=None,
        file_name="ccmas.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        content_sha256=_sha(),
        storage_uri="s3://build-documents/platform/ccmas.pdf",
        created_by="system",
        created_by_email="system@build.internal",
    )
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            await uow.assets.insert_asset(asset)
    return asset.id


@pytest.fixture
async def two_tenants(client):
    a, b = await _tenant(client), await _tenant(client)
    a["source"] = _source(client, a)
    a["asset"] = _asset(client, a, a["source"])
    return a, b


# --- tenant B against tenant A ---------------------------------------------------------------


async def test_another_tenant_cannot_version_or_supersede_an_asset(client, two_tenants):
    a, b = two_tenants

    response = client.post(f"/content/assets/{a['asset']}/version", headers=b["h"], json=_version_body())

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "CONTENT_NOT_FOUND"
    after = _asset_state(client, a, a["asset"])
    assert after["status"] == "active"  # not superseded
    listed = client.get(f"/content/sources/{a['source']}/assets", headers=a["h"]).json()["data"]
    assert [asset["id"] for asset in listed] == [a["asset"]]  # no version was created


async def test_another_tenant_cannot_revoke_an_asset_or_learn_that_it_exists(client, two_tenants):
    a, b = two_tenants

    response = client.post(f"/content/assets/{a['asset']}/revoke", headers=b["h"], json=REASON)
    missing = client.post(f"/content/assets/{uuid4()}/revoke", headers=b["h"], json=REASON)

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()  # the same answer as a missing asset
    assert _asset_state(client, a, a["asset"])["status"] == "active"


async def test_another_tenant_cannot_register_into_a_source_or_learn_its_owner(client, two_tenants):
    a, b = two_tenants

    response = client.post(f"/content/sources/{a['source']}/assets", headers=b["h"], json=_register_body())

    assert response.status_code == 404, response.text
    assert a["id"] not in response.text
    listed = client.get(f"/content/sources/{a['source']}/assets", headers=a["h"]).json()["data"]
    assert [asset["id"] for asset in listed] == [a["asset"]]


async def test_the_owner_tenant_can_still_version_and_revoke(client, two_tenants):
    a, _ = two_tenants

    version = client.post(f"/content/assets/{a['asset']}/version", headers=a["h"], json=_version_body())
    revoke = client.post(f"/content/assets/{version.json()['data']['id']}/revoke", headers=a["h"], json=REASON)

    assert version.status_code == 201, version.text
    assert _asset_state(client, a, a["asset"])["status"] == "superseded"
    assert revoke.status_code == 200, revoke.text


# --- tenants against platform content --------------------------------------------------------


@pytest.mark.parametrize("role", ["lecturer", "admin", "owner"])
async def test_no_tenant_role_can_create_a_platform_source(client, role):
    tenant = await _tenant(client, role)
    code = f"PLAT_{uuid4().hex[:8].upper()}"

    response = client.post(
        "/content/sources",
        headers=tenant["h"],
        json={
            "code": code,
            "name": "Platform attempt",
            "source_type": "ccmas",
            "authority_level": "regulatory",
            "visibility": "platform",
        },
    )

    assert response.status_code == 403, response.text
    listed = client.get("/content/sources", headers=tenant["h"], params={"limit": 100}).text
    assert code not in listed


@pytest.fixture
async def platform_content(client):
    source_id = await seed_platform_source(f"PLAT_{uuid4().hex[:8].upper()}")
    asset_id = await _platform_asset(source_id)
    return {"source": source_id, "asset": asset_id}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", "/content/sources/{source}", {"name": "Hijacked platform name"}),
        ("post", "/content/sources/{source}/deprecate", REASON),
        ("post", "/content/sources/{source}/revoke", REASON),
        ("post", "/content/sources/{source}/activate", {}),
    ],
)
async def test_a_tenant_cannot_change_a_platform_source(client, platform_content, method, path, body):
    tenant = await _tenant(client)
    before = client.get(f"/content/sources/{platform_content['source']}", headers=tenant["h"]).json()["data"]

    response = getattr(client, method)(path.format(**platform_content), headers=tenant["h"], json=body)

    assert response.status_code == 403, response.text
    after = client.get(f"/content/sources/{platform_content['source']}", headers=tenant["h"]).json()["data"]
    assert (after["name"], after["status"]) == (before["name"], before["status"])


async def test_a_tenant_cannot_add_change_or_revoke_platform_assets(client, platform_content):
    tenant = await _tenant(client)

    register = client.post(f"/content/sources/{platform_content['source']}/assets", headers=tenant["h"], json=_register_body())
    version = client.post(f"/content/assets/{platform_content['asset']}/version", headers=tenant["h"], json=_version_body())
    revoke = client.post(f"/content/assets/{platform_content['asset']}/revoke", headers=tenant["h"], json=REASON)

    for response in (register, version, revoke):
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "PLATFORM_CONTENT_NOT_WRITABLE"
    async with SessionLocal() as session:
        async with ContentUnitOfWork(session) as uow:
            platform_asset = await uow.assets.get_asset_by_id(platform_content["asset"])
            assets, total = await uow.assets.list_assets_by_source(platform_content["source"])
    assert platform_asset.status.value == "active"
    assert total == 1 and assets[0].id == platform_content["asset"]


async def test_platform_sources_stay_readable_by_every_tenant(client, platform_content):
    tenant = await _tenant(client)

    response = client.get(f"/content/sources/{platform_content['source']}", headers=tenant["h"])

    assert response.status_code == 200, response.text

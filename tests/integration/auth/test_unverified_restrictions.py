"""Decision D4: unverified accounts may sign in, but get no tenant access."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.dependencies import get_verified_principal
from app.core.principal import AuthenticatedPrincipal
from tests.integration.identity_helpers import verify_email
from tests.integration.tenant.test_tenant_context import seed_tenant_membership

PASSWORD = "StrongPass123!"


def _sign_up_and_in(client):
    email = f"d4-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    login = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return email, user_id, login.json()["data"]["access_token"]


def _headers(token, slug=None):
    headers = {"Authorization": f"Bearer {token}"}
    if slug:
        headers["X-Tenant-Slug"] = slug
    return headers


async def test_unverified_member_can_sign_in_but_not_enter_the_tenant(client):
    _, user_id, token = _sign_up_and_in(client)
    slug = f"d4-{uuid4().hex}"
    await seed_tenant_membership(slug, user_id, role="lecturer")

    assert client.get("/identity/whoami", headers=_headers(token)).status_code == 200
    me = client.get("/identity/me", headers=_headers(token)).json()["data"]
    assert me["email_verified"] is False
    assert me["status"] == "PENDING_VERIFICATION"

    for path in ("/identity/tenant-context", "/identity/permissions", "/identity/authorization-probe"):
        resp = client.get(path, headers=_headers(token, slug))
        assert resp.status_code == 403, path
        assert resp.json()["meta"]["error"] == "email verification required"


async def test_tenant_access_opens_as_soon_as_the_email_is_verified(client):
    email, user_id, token = _sign_up_and_in(client)
    slug = f"d4-{uuid4().hex}"
    tenant_id, _ = await seed_tenant_membership(slug, user_id, role="lecturer")
    assert client.get("/identity/tenant-context", headers=_headers(token, slug)).status_code == 403

    verify_email(client, email)

    # Same token: verification is read from the database on each request.
    resp = client.get("/identity/tenant-context", headers=_headers(token, slug))
    assert resp.status_code == 200
    assert resp.json()["data"]["tenant_id"] == tenant_id
    assert client.get("/identity/authorization-probe", headers=_headers(token, slug)).status_code == 200
    assert client.get("/identity/me", headers=_headers(token)).json()["data"]["email_verified"] is True


async def test_unverified_user_learns_nothing_about_other_tenants(client):
    _, _, token = _sign_up_and_in(client)

    real = client.get("/identity/tenant-context", headers=_headers(token, f"d4-{uuid4().hex}"))
    await seed_tenant_membership(slug := f"d4-{uuid4().hex}", str(uuid4()))
    existing = client.get("/identity/tenant-context", headers=_headers(token, slug))

    assert real.status_code == existing.status_code == 403
    assert real.json()["meta"] == existing.json()["meta"]


async def test_verification_does_not_grant_membership(client):
    email, _, token = _sign_up_and_in(client)
    verify_email(client, email)
    slug = f"d4-{uuid4().hex}"
    await seed_tenant_membership(slug, str(uuid4()))

    resp = client.get("/identity/tenant-context", headers=_headers(token, slug))

    assert resp.status_code == 403
    assert resp.json()["meta"]["error"] == "tenant access denied"


async def test_verified_principal_dependency_rejects_unverified_accounts():
    with pytest.raises(HTTPException) as exc:
        await get_verified_principal(AuthenticatedPrincipal("u", "s", email_verified=False))
    assert exc.value.status_code == 403

    verified = AuthenticatedPrincipal("u", "s", email_verified=True)
    assert await get_verified_principal(verified) is verified

from uuid import uuid4

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from sqlalchemy import update
from tests.integration.identity_helpers import verify_email
from tests.integration.tenant.test_tenant_context import seed_tenant_membership

PASSWORD = "StrongPass123!"


def _account(client, verified=True):
    email = f"mine-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    if verified:
        verify_email(client, email)
    token = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def _set(client, model, row_id, **values):
    async def run():
        async with SessionLocal() as db:
            await db.execute(update(model).where(model.id == row_id).values(**values))
            await db.commit()

    client.portal.call(run)


def _mine(client, headers):
    return client.get("/identity/memberships", headers=headers)


def test_lists_only_the_callers_active_memberships_in_active_tenants(client):
    user_id, headers = _account(client)
    slugs = [f"mine-{uuid4().hex[:10]}" for _ in range(4)]
    seeded = [
        client.portal.call(seed_tenant_membership, slug, user_id, role)
        for slug, role in zip(slugs, ["owner", "lecturer", "student", "student"])
    ]
    other_user, _ = _account(client)
    client.portal.call(seed_tenant_membership, f"other-{uuid4().hex[:10]}", other_user, "admin")
    _set(client, MembershipModel, seeded[2][1], status="archived")  # revoked membership
    _set(client, TenantModel, seeded[3][0], status="archived")  # archived tenant

    resp = _mine(client, headers)

    assert resp.status_code == 200
    assert [(m["tenant_slug"], m["role"]) for m in resp.json()["data"]] == [(slugs[0], "owner"), (slugs[1], "lecturer")]
    assert all(m["tenant_name"] == "FUTA" for m in resp.json()["data"])


def test_requires_authentication_and_works_before_verification(client):
    assert client.get("/identity/memberships").status_code == 401

    user_id, headers = _account(client, verified=False)
    slug = f"mine-{uuid4().hex[:10]}"
    client.portal.call(seed_tenant_membership, slug, user_id, "student")

    listed = _mine(client, headers)
    assert listed.status_code == 200 and [m["tenant_slug"] for m in listed.json()["data"]] == [slug]
    # Listing is not access: tenant requests still require a verified email (D4).
    assert client.get("/identity/tenant-context", headers={**headers, "X-Tenant-Slug": slug}).status_code == 403


def test_a_new_account_has_no_memberships(client):
    _, headers = _account(client)

    assert _mine(client, headers).json()["data"] == []

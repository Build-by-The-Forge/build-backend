from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import (
    MembershipModel,
    TenantJoinPolicyModel,
    TenantModel,
)
from app.infrastructure.identity.models import UserModel, UserStatus
from tests.integration.identity_helpers import verify_email
from tests.integration.tenant.test_tenant_context import seed_tenant_membership

PASSWORD = "StrongPass123!"


def _db(client, fn):
    async def run():
        async with SessionLocal() as db:
            result = await fn(db)
            await db.commit()
            return result

    return client.portal.call(run)


def _account(client, domain="futa.edu.ng", verified=True):
    email = f"j-{uuid4().hex[:12]}@{domain}"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    if verified:
        verify_email(client, email)
    token = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"id": user_id, "email": email, "headers": {"Authorization": f"Bearer {token}"}}


def _tenant(client, enabled=True, domains=("futa.edu.ng",)):
    owner = _account(client, domain="example.com")
    slug = f"join-{uuid4().hex[:10]}"
    tenant_id, _ = client.portal.call(seed_tenant_membership, slug, owner["id"], "owner")
    if domains:
        resp = client.put(
            f"/tenants/{slug}/join-policy",
            json={"enabled": enabled, "allowed_domains": list(domains)},
            headers=owner["headers"],
        )
        assert resp.status_code == 200, resp.text
    return slug, tenant_id, owner


def _join(client, slug, account):
    return client.post(f"/tenants/{slug}/join", headers=account["headers"])


def _memberships(client, tenant_id, user_id):
    return list(
        _db(
            client,
            lambda db: db.scalars(
                select(MembershipModel).where(MembershipModel.tenant_id == tenant_id, MembershipModel.user_id == user_id)
            ),
        )
    )


async def _add_membership(tenant_id, user_id, role):
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        db.add(
            MembershipModel(
                id=str(uuid4()), tenant_id=tenant_id, user_id=user_id, role=role, status="active", created_at=now, updated_at=now
            )
        )
        await db.commit()


def test_a_verified_address_on_the_tenant_domain_joins_as_a_student(client):
    slug, tenant_id, _ = _tenant(client)
    student = _account(client)

    resp = _join(client, slug, student)

    assert resp.status_code == 201, resp.text
    assert (resp.json()["data"]["role"], resp.json()["data"]["created"]) == ("student", True)
    context = client.get("/identity/tenant-context", headers={**student["headers"], "X-Tenant-Slug": slug})
    assert context.status_code == 200 and context.json()["data"]["role"] == "student"


def test_an_unverified_address_cannot_join(client):
    slug, tenant_id, _ = _tenant(client)
    unverified = _account(client, verified=False)

    resp = _join(client, slug, unverified)

    assert resp.status_code == 403 and resp.json()["meta"]["error"] == "email verification required"
    assert _memberships(client, tenant_id, unverified["id"]) == []


@pytest.mark.parametrize(
    "domain",
    ["gmail.com", "student.futa.edu.ng", "evilfuta.edu.ng", "futa.edu.ng.evil.com", "futa.edu.ng.ng"],
)
def test_only_an_exactly_listed_domain_is_eligible(client, domain):
    slug, tenant_id, _ = _tenant(client)
    outsider = _account(client, domain=domain)

    resp = _join(client, slug, outsider)

    assert resp.status_code == 403 and resp.json()["meta"]["error"] == "you are not eligible to join this tenant"
    assert _memberships(client, tenant_id, outsider["id"]) == []


def test_an_explicitly_listed_subdomain_is_eligible(client):
    slug, _, _ = _tenant(client, domains=("futa.edu.ng", "student.futa.edu.ng"))

    assert _join(client, slug, _account(client, domain="student.futa.edu.ng")).status_code == 201


def test_no_policy_or_a_disabled_policy_admits_nobody(client):
    no_policy_slug, _, _ = _tenant(client, domains=())
    disabled_slug, _, _ = _tenant(client, enabled=False)
    student = _account(client)

    assert _join(client, no_policy_slug, student).status_code == 403
    assert _join(client, disabled_slug, student).status_code == 403


def test_an_existing_member_keeps_their_role(client):
    slug, tenant_id, _ = _tenant(client)
    lecturer = _account(client)
    client.portal.call(_add_membership, tenant_id, lecturer["id"], "lecturer")

    resp = _join(client, slug, lecturer)

    assert resp.status_code == 200
    assert (resp.json()["data"]["role"], resp.json()["data"]["created"]) == ("lecturer", False)
    assert [m.role for m in _memberships(client, tenant_id, lecturer["id"])] == ["lecturer"]


def test_joining_twice_is_idempotent(client):
    slug, tenant_id, _ = _tenant(client)
    student = _account(client)

    first, second = _join(client, slug, student), _join(client, slug, student)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["data"]["membership_id"] == second.json()["data"]["membership_id"]
    assert len(_memberships(client, tenant_id, student["id"])) == 1


def test_a_revoked_member_cannot_rejoin_by_domain(client):
    slug, tenant_id, owner = _tenant(client)
    student = _account(client)
    membership_id = _join(client, slug, student).json()["data"]["membership_id"]
    assert client.delete(f"/tenants/{slug}/members/{membership_id}", headers=owner["headers"]).status_code == 200

    resp = _join(client, slug, student)

    assert resp.status_code == 403 and "revoked" in resp.json()["meta"]["error"]
    assert [m.status for m in _memberships(client, tenant_id, student["id"])] == ["archived"]


@pytest.mark.parametrize("status", [UserStatus.DISABLED, UserStatus.LOCKED, UserStatus.DELETED])
def test_blocked_accounts_cannot_join(client, status):
    slug, tenant_id, _ = _tenant(client)
    student = _account(client)
    _db(client, lambda db: db.execute(update(UserModel).where(UserModel.id == student["id"]).values(status=status)))

    assert _join(client, slug, student).status_code == 401
    assert _memberships(client, tenant_id, student["id"]) == []


def test_changing_the_policy_does_not_touch_existing_members(client):
    slug, _, owner = _tenant(client)
    student = _account(client)
    _join(client, slug, student)

    client.put(f"/tenants/{slug}/join-policy", json={"enabled": False, "allowed_domains": []}, headers=owner["headers"])

    context = client.get("/identity/tenant-context", headers={**student["headers"], "X-Tenant-Slug": slug})
    assert context.status_code == 200 and context.json()["data"]["role"] == "student"
    assert _join(client, slug, _account(client)).status_code == 403


@pytest.mark.parametrize("role", ["lecturer", "hod", "faculty_admin", "admin", "owner"])
def test_a_policy_can_never_grant_a_staff_role(client, role):
    slug, tenant_id, owner = _tenant(client)

    resp = client.put(
        f"/tenants/{slug}/join-policy",
        json={"enabled": True, "allowed_domains": ["futa.edu.ng"], "default_role": role},
        headers=owner["headers"],
    )
    assert resp.status_code == 422

    # Even a policy row edited by hand to grant the role admits nobody.
    _db(
        client,
        lambda db: db.execute(
            update(TenantJoinPolicyModel).where(TenantJoinPolicyModel.tenant_id == tenant_id).values(default_role=role)
        ),
    )
    joiner = _account(client)
    assert _join(client, slug, joiner).status_code == 403
    assert _memberships(client, tenant_id, joiner["id"]) == []


def test_unknown_and_archived_tenants_are_not_found(client):
    slug, tenant_id, _ = _tenant(client)
    student = _account(client)
    assert _join(client, f"nope-{uuid4().hex[:8]}", student).status_code == 404

    _db(client, lambda db: db.execute(update(TenantModel).where(TenantModel.id == tenant_id).values(status="archived")))
    assert _join(client, slug, student).status_code == 404


def test_only_settings_managers_see_or_change_the_policy(client):
    slug, tenant_id, owner = _tenant(client)
    hod = _account(client)
    client.portal.call(_add_membership, tenant_id, hod["id"], "hod")

    policy = client.get(f"/tenants/{slug}/join-policy", headers=owner["headers"])
    assert policy.json()["data"]["allowed_domains"] == ["futa.edu.ng"]
    assert client.get(f"/tenants/{slug}/join-policy", headers=hod["headers"]).status_code == 403
    change = client.put(
        f"/tenants/{slug}/join-policy", json={"enabled": True, "allowed_domains": ["x.edu"]}, headers=hod["headers"]
    )
    assert change.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"enabled": True, "allowed_domains": ["*.futa.edu.ng"]},
        {"enabled": True, "allowed_domains": ["@futa.edu.ng"]},
        {"enabled": True, "allowed_domains": []},
        {"enabled": "yes", "allowed_domains": ["futa.edu.ng"]},
        {"enabled": True, "allowed_domains": "futa.edu.ng"},
    ],
)
def test_invalid_policies_are_rejected(client, body):
    slug, _, owner = _tenant(client)

    assert client.put(f"/tenants/{slug}/join-policy", json=body, headers=owner["headers"]).status_code == 422

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel
from app.infrastructure.identity.models import SecurityEventModel
from sqlalchemy import select
from tests.integration.identity_helpers import verify_email
from tests.integration.tenant.test_tenant_context import seed_tenant_membership

PASSWORD = "StrongPass123!"


def _account(client):
    email = f"mem-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    verify_email(client, email)
    token = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"id": user_id, "email": email, "headers": {"Authorization": f"Bearer {token}"}}


async def _add(tenant_id, user_id, role, status="active"):
    now = datetime.now(timezone.utc)
    membership_id = str(uuid4())
    async with SessionLocal() as db:
        db.add(
            MembershipModel(
                id=membership_id, tenant_id=tenant_id, user_id=user_id, role=role, status=status, created_at=now, updated_at=now
            )
        )
        await db.commit()
    return membership_id


def _tenant(client, *roles):
    """A tenant with one verified member per role; returns slug, tenant id, members."""
    first = _account(client)
    slug = f"mem-{uuid4().hex[:10]}"
    tenant_id, membership_id = client.portal.call(seed_tenant_membership, slug, first["id"], roles[0])
    members = [{**first, "membership_id": membership_id, "role": roles[0]}]
    for role in roles[1:]:
        account = _account(client)
        members.append({**account, "membership_id": client.portal.call(_add, tenant_id, account["id"], role), "role": role})
    return slug, tenant_id, members


def _patch(client, slug, actor, target, role):
    return client.patch(f"/tenants/{slug}/members/{target['membership_id']}", json={"role": role}, headers=actor["headers"])


def _revoke(client, slug, actor, target):
    return client.delete(f"/tenants/{slug}/members/{target['membership_id']}", headers=actor["headers"])


def _stored(client, membership_id):
    async def run():
        async with SessionLocal() as db:
            return await db.get(MembershipModel, membership_id)

    return client.portal.call(run)


def _in_tenant(client, member, slug):
    return client.get("/identity/tenant-context", headers={**member["headers"], "X-Tenant-Slug": slug}).status_code


def test_members_are_listed_for_roles_with_read_permission(client):
    slug, _, (admin, hod, student) = _tenant(client, "admin", "hod", "student")

    listed = client.get(f"/tenants/{slug}/members", headers=admin["headers"])

    assert listed.status_code == 200
    assert {(m["email"], m["role"]) for m in listed.json()["data"]} == {
        (admin["email"], "admin"),
        (hod["email"], "hod"),
        (student["email"], "student"),
    }
    assert client.get(f"/tenants/{slug}/members", headers=hod["headers"]).status_code == 200
    assert client.get(f"/tenants/{slug}/members", headers=student["headers"]).status_code == 403


@pytest.mark.parametrize(
    "actor_role, target_role, new_role, expected",
    [
        ("owner", "admin", "lecturer", 200),
        ("owner", "student", "owner", 200),
        ("owner", "owner", "admin", 200),  # another owner remains (the actor)
        ("admin", "student", "lecturer", 200),
        ("admin", "lecturer", "faculty_admin", 200),
        ("admin", "student", "admin", 403),  # cannot grant own rank
        ("admin", "admin", "student", 403),  # cannot manage own rank
        ("admin", "owner", "student", 403),
        ("faculty_admin", "student", "lecturer", 403),  # no manage permission
        ("hod", "student", "lecturer", 403),
        ("student", "student", "lecturer", 403),
    ],
)
def test_role_changes_follow_the_hierarchy(client, actor_role, target_role, new_role, expected):
    slug, _, (actor, target) = _tenant(client, actor_role, target_role)

    resp = _patch(client, slug, actor, target, new_role)

    assert resp.status_code == expected, resp.text
    assert _stored(client, target["membership_id"]).role == (new_role if expected == 200 else target_role)


def test_nobody_changes_or_revokes_their_own_membership(client):
    slug, _, (owner, other_owner) = _tenant(client, "owner", "owner")

    assert _patch(client, slug, owner, owner, "admin").status_code == 403
    assert _revoke(client, slug, owner, owner).status_code == 403
    assert _stored(client, owner["membership_id"]).role == "owner"


def test_a_demoted_caller_cannot_act_on_their_old_role(client):
    slug, _, (owner_a, owner_b, student) = _tenant(client, "owner", "owner", "student")

    assert _patch(client, slug, owner_a, owner_b, "lecturer").status_code == 200

    # owner_b's token is unchanged, but their role is re-read for every change.
    assert _patch(client, slug, owner_b, student, "lecturer").status_code == 403
    assert _patch(client, slug, owner_b, owner_a, "student").status_code == 403
    assert _stored(client, owner_a["membership_id"]).role == "owner"


def test_revoking_a_membership_removes_access_at_once_and_can_be_undone(client):
    slug, _, (admin, student) = _tenant(client, "admin", "student")
    assert _in_tenant(client, student, slug) == 200

    revoked = _revoke(client, slug, admin, student)

    assert revoked.status_code == 200 and revoked.json()["data"]["status"] == "archived"
    assert _in_tenant(client, student, slug) == 403
    assert _revoke(client, slug, admin, student).status_code == 409
    assert _patch(client, slug, admin, student, "lecturer").status_code == 409

    back = client.post(f"/tenants/{slug}/members/{student['membership_id']}/reactivate", headers=admin["headers"])
    assert back.status_code == 200 and back.json()["data"]["status"] == "active"
    assert _in_tenant(client, student, slug) == 200


def test_reactivation_is_bounded_by_the_grant_hierarchy(client):
    slug, tenant_id, (admin,) = _tenant(client, "admin")
    archived_admin = _account(client)
    membership_id = client.portal.call(_add, tenant_id, archived_admin["id"], "admin", "archived")

    resp = client.post(f"/tenants/{slug}/members/{membership_id}/reactivate", headers=admin["headers"])

    assert resp.status_code == 403


def test_members_of_one_tenant_cannot_touch_another(client):
    slug_a, _, (admin_a,) = _tenant(client, "admin")
    slug_b, _, (owner_b, student_b) = _tenant(client, "owner", "student")

    # Through tenant A's path, tenant B's membership does not exist.
    assert _patch(client, slug_a, admin_a, student_b, "lecturer").status_code == 404
    assert _revoke(client, slug_a, admin_a, student_b).status_code == 404
    # Through tenant B's path, admin_a is not a member at all.
    assert _patch(client, slug_b, admin_a, student_b, "lecturer").status_code == 403
    assert _stored(client, student_b["membership_id"]).role == "student"


def test_unknown_roles_and_missing_members(client):
    slug, _, (owner, student) = _tenant(client, "owner", "student")

    assert _patch(client, slug, owner, student, "superuser").status_code == 422
    assert (
        client.patch(f"/tenants/{slug}/members/{uuid4()}", json={"role": "lecturer"}, headers=owner["headers"]).status_code == 404
    )


def test_membership_changes_are_audited(client):
    slug, tenant_id, (owner, student) = _tenant(client, "owner", "student")
    _patch(client, slug, owner, student, "lecturer")
    _revoke(client, slug, owner, student)
    client.post(f"/tenants/{slug}/members/{student['membership_id']}/reactivate", headers=owner["headers"])

    async def events():
        async with SessionLocal() as db:
            rows = await db.scalars(
                select(SecurityEventModel)
                .where(SecurityEventModel.event_type == "membership", SecurityEventModel.user_id == owner["id"])
                .order_by(SecurityEventModel.created_at)
            )
            return [(r.action, json.loads(r.meta_data)) for r in rows]

    recorded = client.portal.call(events)
    assert [action for action, _ in recorded] == ["role_changed", "revoked", "reactivated"]
    assert recorded[0][1] | {"request_id": None} == {
        "request_id": None,
        "tenant_id": tenant_id,
        "membership_id": student["membership_id"],
        "member_user_id": student["id"],
        "from_role": "student",
        "to_role": "lecturer",
    }

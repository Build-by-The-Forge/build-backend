import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.api import tenant_invitations as invitations_api
from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantInvitationModel
from app.infrastructure.identity.models import SecurityEventModel
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


def _account(client, *, verified=True, email=None):
    email = email or f"inv-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    if verified:
        verify_email(client, email)
    token = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"id": user_id, "email": email, "headers": {"Authorization": f"Bearer {token}"}}


def _tenant_with(client, role):
    """A fresh tenant and a verified member with ``role`` in it."""
    actor = _account(client)
    slug = f"inv-{uuid4().hex[:10]}"
    tenant_id, membership_id = client.portal.call(seed_tenant_membership, slug, actor["id"], role)
    return slug, tenant_id, actor


def _invite(client, slug, actor, email, role, **extra):
    return client.post(f"/tenants/{slug}/invitations", json={"email": email, "role": role, **extra}, headers=actor["headers"])


def _code(email):
    sender = invitations_api.service._email_sender
    message = next(m for m in reversed(sender.messages) if m.to == email and "invited" in m.subject)
    return message.body.split("\n\n")[1]


def _accept(client, account, token):
    return client.post("/invitations/accept", json={"token": token}, headers=account["headers"])


def _membership(client, tenant_id, user_id):
    return _db(
        client,
        lambda db: db.scalar(
            select(MembershipModel).where(MembershipModel.tenant_id == tenant_id, MembershipModel.user_id == user_id)
        ),
    )


def test_invite_and_accept_creates_the_membership(client):
    slug, tenant_id, admin = _tenant_with(client, "admin")
    invitee_email = f"lect-{uuid4().hex}@example.com"

    created = _invite(client, slug, admin, invitee_email, "lecturer")

    assert created.status_code == 201, created.text
    body = created.json()["data"]
    assert (body["email"], body["role"], body["status"]) == (invitee_email, "lecturer", "pending")
    assert "token" not in created.text and "token_hash" not in created.text
    code = _code(invitee_email)
    assert code not in created.text

    invitee = _account(client, email=invitee_email)
    accepted = _accept(client, invitee, code)

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["role"] == "lecturer" and accepted.json()["data"]["tenant_slug"] == slug
    context = client.get("/identity/tenant-context", headers={**invitee["headers"], "X-Tenant-Slug": slug})
    assert context.status_code == 200 and context.json()["data"]["role"] == "lecturer"
    listed = client.get(f"/tenants/{slug}/invitations?status=accepted", headers=admin["headers"]).json()["data"]
    assert [i["email"] for i in listed] == [invitee_email]


@pytest.mark.parametrize(
    "actor_role, role, expected",
    [
        ("owner", "owner", 201),
        ("owner", "admin", 201),
        ("admin", "owner", 403),
        ("admin", "admin", 403),
        ("admin", "faculty_admin", 201),
        ("faculty_admin", "faculty_admin", 403),
        ("faculty_admin", "hod", 201),
        ("hod", "admin", 403),
        ("hod", "hod", 403),
        ("hod", "lecturer", 201),
        ("hod", "student", 201),
        ("lecturer", "student", 403),  # no invite permission at all
        ("student", "student", 403),
    ],
)
def test_inviting_follows_the_grant_hierarchy(client, actor_role, role, expected):
    slug, _, actor = _tenant_with(client, actor_role)

    resp = _invite(client, slug, actor, f"x-{uuid4().hex}@example.com", role)

    assert resp.status_code == expected, resp.text


def test_unknown_roles_and_bad_emails_are_rejected(client):
    slug, _, owner = _tenant_with(client, "owner")

    assert _invite(client, slug, owner, f"x-{uuid4().hex}@example.com", "superuser").status_code == 422
    assert _invite(client, slug, owner, "not-an-email", "student").status_code == 422


def test_the_tenant_comes_from_the_path_not_the_payload(client):
    slug, tenant_id, admin = _tenant_with(client, "admin")
    other_slug, other_tenant_id, _ = _tenant_with(client, "owner")

    resp = _invite(client, slug, admin, f"x-{uuid4().hex}@example.com", "student", tenant_id=other_tenant_id)

    assert resp.status_code == 201
    stored = _db(client, lambda db: db.get(TenantInvitationModel, resp.json()["data"]["id"]))
    assert stored.tenant_id == tenant_id


def test_members_cannot_invite_into_another_tenant(client):
    slug, _, admin = _tenant_with(client, "admin")
    other_slug, _, other_owner = _tenant_with(client, "owner")

    assert _invite(client, other_slug, admin, f"x-{uuid4().hex}@example.com", "student").status_code == 403
    theirs = _invite(client, other_slug, other_owner, f"x-{uuid4().hex}@example.com", "student").json()["data"]
    assert client.delete(f"/tenants/{slug}/invitations/{theirs['id']}", headers=admin["headers"]).status_code == 404


def test_an_unverified_inviter_is_refused(client):
    actor = _account(client, verified=False)
    slug = f"inv-{uuid4().hex[:10]}"
    client.portal.call(seed_tenant_membership, slug, actor["id"], "owner")

    resp = _invite(client, slug, actor, f"x-{uuid4().hex}@example.com", "student")

    assert resp.status_code == 403 and resp.json()["meta"]["error"] == "email verification required"


def test_inviting_an_existing_active_member_is_refused(client):
    slug, _, owner = _tenant_with(client, "owner")
    member = _account(client)
    _invite(client, slug, owner, member["email"], "student")
    _accept(client, member, _code(member["email"]))

    assert _invite(client, slug, owner, member["email"], "lecturer").status_code == 409


def test_accepting_never_changes_an_active_membership(client):
    slug, tenant_id, owner = _tenant_with(client, "owner")
    member = _account(client)
    _invite(client, slug, owner, member["email"], "student")
    _accept(client, member, _code(member["email"]))
    # A second invitation for a higher role, created before the first was accepted, is
    # simulated by inserting it directly: the API itself refuses to invite members.
    _invite(client, slug, owner, f"y-{uuid4().hex}@example.com", "admin")
    _db(
        client,
        lambda db: db.execute(
            update(TenantInvitationModel)
            .where(TenantInvitationModel.tenant_id == tenant_id, TenantInvitationModel.role == "admin")
            .values(email=member["email"])
        ),
    )
    admin_code = _code_for_role(client, tenant_id)

    resp = _accept(client, member, admin_code)

    assert resp.status_code == 409
    assert _membership(client, tenant_id, member["id"]).role == "student"


def _code_for_role(client, tenant_id):
    sender = invitations_api.service._email_sender
    return next(m for m in reversed(sender.messages) if "as admin" in m.body).body.split("\n\n")[1]


def test_an_archived_member_is_reactivated_with_the_invited_role(client):
    slug, tenant_id, owner = _tenant_with(client, "owner")
    member = _account(client)
    _invite(client, slug, owner, member["email"], "lecturer")
    _accept(client, member, _code(member["email"]))
    _db(
        client,
        lambda db: db.execute(
            update(MembershipModel)
            .where(MembershipModel.tenant_id == tenant_id, MembershipModel.user_id == member["id"])
            .values(status="archived")
        ),
    )

    _invite(client, slug, owner, member["email"], "student")
    resp = _accept(client, member, _code(member["email"]))

    assert resp.status_code == 200 and resp.json()["data"]["reactivated"] is True
    stored = _membership(client, tenant_id, member["id"])
    assert (stored.role, stored.status) == ("student", "active")


def test_accept_requires_the_invited_verified_account(client):
    slug, _, owner = _tenant_with(client, "owner")
    invited_email = f"who-{uuid4().hex}@example.com"
    _invite(client, slug, owner, invited_email, "student")
    code = _code(invited_email)

    unverified = _account(client, verified=False, email=invited_email)
    resp = _accept(client, unverified, code)
    assert resp.status_code == 403 and resp.json()["meta"]["error"] == "email verification required"

    someone_else = _account(client)
    assert _accept(client, someone_else, code).status_code == 403


def test_invalid_reused_revoked_and_expired_invitations_are_refused(client):
    slug, tenant_id, owner = _tenant_with(client, "owner")
    assert _accept(client, owner, "not-a-real-code").status_code == 404

    used_email = f"used-{uuid4().hex}@example.com"
    _invite(client, slug, owner, used_email, "student")
    used = _account(client, email=used_email)
    code = _code(used_email)
    assert _accept(client, used, code).status_code == 200
    assert _accept(client, used, code).status_code == 409

    revoked_email = f"rev-{uuid4().hex}@example.com"
    invitation = _invite(client, slug, owner, revoked_email, "student").json()["data"]
    assert client.delete(f"/tenants/{slug}/invitations/{invitation['id']}", headers=owner["headers"]).status_code == 200
    assert _accept(client, _account(client, email=revoked_email), _code(revoked_email)).status_code == 409

    expired_email = f"exp-{uuid4().hex}@example.com"
    invitation = _invite(client, slug, owner, expired_email, "student").json()["data"]
    _db(
        client,
        lambda db: db.execute(
            update(TenantInvitationModel)
            .where(TenantInvitationModel.id == invitation["id"])
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        ),
    )
    assert _accept(client, _account(client, email=expired_email), _code(expired_email)).status_code == 409


def test_reinviting_replaces_the_outstanding_invitation(client):
    slug, _, owner = _tenant_with(client, "owner")
    email = f"re-{uuid4().hex}@example.com"
    _invite(client, slug, owner, email, "student")
    first = _code(email)
    _invite(client, slug, owner, email, "lecturer")
    second = _code(email)
    invitee = _account(client, email=email)

    assert _accept(client, invitee, first).status_code == 409
    resp = _accept(client, invitee, second)
    assert resp.status_code == 200 and resp.json()["data"]["role"] == "lecturer"


def test_revoking_is_bounded_by_the_grant_hierarchy(client):
    slug, tenant_id, owner = _tenant_with(client, "owner")
    hod = _account(client)
    client.portal.call(_add_member, tenant_id, hod["id"], "hod")
    admin_invite = _invite(client, slug, owner, f"a-{uuid4().hex}@example.com", "admin").json()["data"]
    student_invite = _invite(client, slug, hod, f"s-{uuid4().hex}@example.com", "student").json()["data"]

    assert client.delete(f"/tenants/{slug}/invitations/{admin_invite['id']}", headers=hod["headers"]).status_code == 403
    assert client.delete(f"/tenants/{slug}/invitations/{student_invite['id']}", headers=hod["headers"]).status_code == 200


async def _add_member(tenant_id, user_id, role):
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        db.add(
            MembershipModel(
                id=str(uuid4()), tenant_id=tenant_id, user_id=user_id, role=role, status="active", created_at=now, updated_at=now
            )
        )
        await db.commit()


def test_invitation_events_are_audited(client):
    slug, tenant_id, owner = _tenant_with(client, "owner")
    email = f"aud-{uuid4().hex}@example.com"
    invitation = _invite(client, slug, owner, email, "student").json()["data"]
    invitee = _account(client, email=email)
    _accept(client, invitee, _code(email))

    rows = _db(
        client,
        lambda db: db.scalars(select(SecurityEventModel).where(SecurityEventModel.event_type == "invitation")),
    )
    events = {(r.action, r.user_id): json.loads(r.meta_data) for r in rows if invitation["id"] in (r.meta_data or "")}
    assert events[("created", owner["id"])]["tenant_id"] == tenant_id
    assert events[("accepted", invitee["id"])]["role"] == "student"
    assert all(email not in json.dumps(meta) for meta in events.values())

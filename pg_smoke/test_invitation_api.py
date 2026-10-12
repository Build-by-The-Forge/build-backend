import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.api import identity as identity_api
from app.api import tenant_invitations as invitations_api
from app.db.session import SessionLocal
from pg_smoke.test_provisioning_cli import _cli

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "StrongPass123!"


async def _account(client, email=None):
    email = email or f"pgi-{uuid4().hex}@example.com"
    await client.post("/identity/users", json={"email": email, "password": PASSWORD})
    message = identity_api.service.email_sender.latest_to(email, "Verify your BUILD email address")
    await client.post("/identity/verify-email", json={"token": message.body.split("\n\n")[1]})
    login = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    return email, {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def test_invitation_flow_on_the_migrated_schema(client):
    slug, owner_email = f"pgi-{uuid4().hex[:10]}", f"owner-{uuid4().hex}@example.com"
    # A subprocess, as in production: running the command in-process would
    # leave connections from its own event loop in the shared pool.
    code, out = await _cli("--name", "PG Invite University", "--slug", slug, "--owner-email", owner_email, password=PASSWORD)
    assert code == 0, out
    login = await client.post("/identity/authenticate", json={"email": owner_email, "password": PASSWORD})
    owner = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    invitee_email = f"lect-{uuid4().hex}@example.com"
    created = await client.post(f"/tenants/{slug}/invitations", json={"email": invitee_email, "role": "lecturer"}, headers=owner)
    assert created.status_code == 201, created.text
    sender = invitations_api.service._email_sender
    code = next(m for m in reversed(sender.messages) if m.to == invitee_email).body.split("\n\n")[1]

    _, invitee = await _account(client, invitee_email)
    results = await asyncio.gather(*[client.post("/invitations/accept", json={"token": code}, headers=invitee) for _ in range(5)])

    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409], [r.text for r in results]
    context = await client.get("/identity/tenant-context", headers={**invitee, "X-Tenant-Slug": slug})
    assert context.json()["data"]["role"] == "lecturer"
    async with SessionLocal() as session:
        count = (
            await session.execute(
                text(
                    "select count(*) from memberships m join tenants t on t.id = m.tenant_id "
                    "join users u on u.id = m.user_id where t.slug = :slug and u.email = :email"
                ),
                {"slug": slug, "email": invitee_email},
            )
        ).scalar_one()
    assert count == 1

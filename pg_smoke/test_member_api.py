import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.api import identity as identity_api
from app.db.session import SessionLocal
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "StrongPass123!"


async def _owner(client, tenant_id: str) -> dict[str, object]:
    email = f"own-{uuid4().hex}@example.com"
    user_id = (await client.post("/identity/users", json={"email": email, "password": PASSWORD})).json()["data"]["id"]
    message = identity_api.service.email_sender.latest_to(email, "Verify your BUILD email address")
    await client.post("/identity/verify-email", json={"token": message.body.split("\n\n")[1]})
    login = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    membership_id = str(uuid4())
    async with SessionLocal() as session:
        await session.execute(
            text(
                "insert into memberships (id, tenant_id, user_id, role, status, created_at, updated_at) "
                "values (:id, :t, :u, 'owner', 'active', :now, :now)"
            ),
            {"id": membership_id, "t": tenant_id, "u": user_id, "now": datetime.now(timezone.utc)},
        )
        await session.commit()
    return {"membership_id": membership_id, "headers": {"Authorization": f"Bearer {login.json()['data']['access_token']}"}}


async def test_two_owners_demoting_each_other_never_leave_a_tenant_ownerless(client):
    outcomes = []
    for _ in range(10):
        tenant_id, slug = str(uuid4()), f"own-{uuid4().hex[:10]}"
        async with SessionLocal() as session:
            await session.execute(
                text(
                    "insert into tenants (id, name, slug, status, created_at, updated_at) "
                    "values (:id, 'Owners', :slug, 'active', :now, :now)"
                ),
                {"id": tenant_id, "slug": slug, "now": datetime.now(timezone.utc)},
            )
            await session.commit()
        a, b = await _owner(client, tenant_id), await _owner(client, tenant_id)

        responses = await asyncio.gather(
            client.patch(f"/tenants/{slug}/members/{b['membership_id']}", json={"role": "lecturer"}, headers=a["headers"]),
            client.patch(f"/tenants/{slug}/members/{a['membership_id']}", json={"role": "lecturer"}, headers=b["headers"]),
        )
        async with SessionLocal() as session:
            owners = (
                await session.execute(
                    text("select count(*) from memberships where tenant_id = :t and role = 'owner' and status = 'active'"),
                    {"t": tenant_id},
                )
            ).scalar_one()
        outcomes.append((sorted(r.status_code for r in responses), owners))

    assert all(owners == 1 for _, owners in outcomes), outcomes
    assert all(codes[0] == 200 and codes[1] in (403, 409) for codes, _ in outcomes), outcomes

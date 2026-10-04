import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.api import identity as identity_api
from app.db.session import SessionLocal
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "StrongPass123!"


async def _account(client, domain: str) -> tuple[str, dict[str, str]]:
    email = f"dj-{uuid4().hex[:12]}@{domain}"
    user_id = (await client.post("/identity/users", json={"email": email, "password": PASSWORD})).json()["data"]["id"]
    message = identity_api.service.email_sender.latest_to(email, "Verify your BUILD email address")
    await client.post("/identity/verify-email", json={"token": message.body.split("\n\n")[1]})
    login = await client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})
    return user_id, {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def test_concurrent_domain_joins_create_exactly_one_student_membership(client):
    owner_id, owner = await _account(client, "example.com")
    tenant_id, slug = str(uuid4()), f"dj-{uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        await session.execute(
            text(
                "insert into tenants (id, name, slug, status, created_at, updated_at) "
                "values (:id, 'Join U', :slug, 'active', :now, :now)"
            ),
            {"id": tenant_id, "slug": slug, "now": now},
        )
        await session.execute(
            text(
                "insert into memberships (id, tenant_id, user_id, role, status, created_at, updated_at) "
                "values (:id, :t, :u, 'owner', 'active', :now, :now)"
            ),
            {"id": str(uuid4()), "t": tenant_id, "u": owner_id, "now": now},
        )
        await session.commit()
    policy = await client.put(
        f"/tenants/{slug}/join-policy", json={"enabled": True, "allowed_domains": ["futa.edu.ng"]}, headers=owner
    )
    assert policy.status_code == 200, policy.text
    student_id, student = await _account(client, "futa.edu.ng")

    responses = await asyncio.gather(*[client.post(f"/tenants/{slug}/join", headers=student) for _ in range(5)])

    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201], [r.text for r in responses]
    assert len({r.json()["data"]["membership_id"] for r in responses}) == 1
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text("select role, status from memberships where tenant_id = :t and user_id = :u"),
                {"t": tenant_id, "u": student_id},
            )
        ).all()
    assert [tuple(r) for r in rows] == [("student", "active")]

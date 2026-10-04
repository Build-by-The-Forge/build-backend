from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from app.infrastructure.identity.models import UserModel, UserStatus
from tests.integration.identity_helpers import verify_email


async def seed_tenant_membership(
    tenant_slug: str, user_id: str, role: str = "student"
) -> tuple[str, str]:
    """Create a tenant with one membership for ``user_id``.

    Valid on PostgreSQL, where foreign keys are enforced: the tenant row is
    flushed before the membership, and a user id with no account behind it
    (tests use a random id for "someone else") gets a placeholder user.
    """
    tenant_id = str(uuid4())
    membership_id = str(uuid4())
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        if await session.get(UserModel, user_id) is None:
            session.add(
                UserModel(
                    id=user_id,
                    email=f"placeholder-{user_id}@example.com",
                    password_hash="unusable",
                    status=UserStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            TenantModel(
                id=tenant_id,
                name="FUTA",
                slug=tenant_slug,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            MembershipModel(
                id=membership_id,
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    return tenant_id, membership_id


async def authenticate_user(client, email: str) -> tuple[str, str]:
    payload = {"email": email, "password": "StrongPass123!"}
    registered = client.post("/identity/users", json=payload)
    assert registered.status_code == 201
    verify_email(client, payload["email"])
    user_id = registered.json()["data"]["id"]

    authenticated = client.post("/identity/authenticate", json=payload)
    assert authenticated.status_code == 200
    return user_id, authenticated.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_tenant_context_requires_authentication(client):
    response = client.get("/identity/tenant-context", headers={"X-Tenant-Slug": "futa"})

    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_tenant_context_requires_explicit_tenant(client):
    _, access_token = await authenticate_user(client, f"context-{uuid4()}@example.com")

    response = client.get(
        "/identity/tenant-context",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_tenant_context_resolves_active_membership(client):
    user_id, access_token = await authenticate_user(
        client, f"member-{uuid4()}@example.com"
    )
    tenant_slug = f"futa-{uuid4()}"
    tenant_id, membership_id = await seed_tenant_membership(
        tenant_slug, user_id, role="lecturer"
    )

    response = client.get(
        "/identity/tenant-context",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "membership_id": membership_id,
        "role": "lecturer",
    }


@pytest.mark.asyncio
async def test_tenant_context_denies_non_member(client):
    user_id, access_token = await authenticate_user(
        client, f"non-member-{uuid4()}@example.com"
    )
    tenant_slug = f"private-{uuid4()}"
    await seed_tenant_membership(f"member-{uuid4()}", user_id)
    await seed_tenant_membership(tenant_slug, str(uuid4()))

    response = client.get(
        "/identity/tenant-context",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": tenant_slug,
        },
    )

    assert response.status_code == 403
    assert response.json()["success"] is False

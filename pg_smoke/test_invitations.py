import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.domain.tenant.invitation import InvitationStatus, TenantInvitation
from app.domain.tenant.value_objects import MembershipRole, TenantId
from app.infrastructure.tenant.invitation_repository import (
    SQLAlchemyTenantInvitationRepository,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _tenant() -> str:
    tenant_id = str(uuid4())
    async with SessionLocal() as session:
        await session.execute(
            text(
                "insert into tenants (id, name, slug, status, created_at, updated_at) "
                "values (:id, 'Invites', :slug, 'active', :now, :now)"
            ),
            {"id": tenant_id, "slug": f"inv-{uuid4().hex[:10]}", "now": datetime.now(timezone.utc)},
        )
        await session.commit()
    return tenant_id


async def _user() -> str:
    user_id = str(uuid4())
    async with SessionLocal() as session:
        await session.execute(
            text(
                "insert into users (id, email, password_hash, status, created_at, updated_at) "
                "values (:id, :email, 'unusable', 'ACTIVE', :now, :now)"
            ),
            {"id": user_id, "email": f"inv-{user_id}@example.com", "now": datetime.now(timezone.utc)},
        )
        await session.commit()
    return user_id


def _issue(tenant_id: str) -> TenantInvitation:
    return TenantInvitation.issue(
        tenant_id=TenantId(tenant_id),
        email="ada@futa.edu.ng",
        role=MembershipRole.STUDENT,
        token_hash=uuid4().hex + uuid4().hex,
        invited_by_user_id=None,
    )


async def _add(invitation: TenantInvitation) -> None:
    async with SessionLocal() as session:
        await SQLAlchemyTenantInvitationRepository(session).add(invitation)
        await session.commit()


async def test_one_pending_invitation_per_email_is_enforced_by_postgresql():
    tenant_id = await _tenant()
    first = _issue(tenant_id)
    await _add(first)

    with pytest.raises(IntegrityError):
        await _add(_issue(tenant_id))

    async with SessionLocal() as session:
        repo = SQLAlchemyTenantInvitationRepository(session)
        first.revoke()
        assert await repo.mark_revoked(first)
        await session.commit()
    await _add(_issue(tenant_id))  # allowed once the first is no longer pending


async def test_concurrent_accepts_have_exactly_one_winner():
    invitation = _issue(await _tenant())
    await _add(invitation)

    user_ids = [await _user() for _ in range(5)]
    # Every request has already read the invitation as pending; only the
    # conditional UPDATE can stop the extra acceptances.
    sessions = [SessionLocal() for _ in user_ids]
    copies = []
    for session, user_id in zip(sessions, user_ids):
        copy = await SQLAlchemyTenantInvitationRepository(session).get_by_id(invitation.id)
        copy.accept(user_id=user_id, user_email=copy.email, email_verified=True)
        copies.append(copy)

    async def persist(session, copy) -> bool:
        won = await SQLAlchemyTenantInvitationRepository(session).mark_accepted(copy)
        await session.commit()
        return won

    try:
        results = await asyncio.gather(*[persist(s, c) for s, c in zip(sessions, copies)])
    finally:
        for session in sessions:
            await session.close()

    assert sorted(results) == [False, False, False, False, True]
    async with SessionLocal() as session:
        stored = await SQLAlchemyTenantInvitationRepository(session).get_by_id(invitation.id)
    winner = user_ids[results.index(True)]
    assert (stored.status, stored.accepted_by_user_id) == (InvitationStatus.ACCEPTED, winner)


async def test_deleting_a_tenant_removes_its_invitations():
    tenant_id = await _tenant()
    invitation = _issue(tenant_id)
    await _add(invitation)

    async with SessionLocal() as session:
        await session.execute(text("delete from tenants where id = :id"), {"id": tenant_id})
        await session.commit()
        assert await SQLAlchemyTenantInvitationRepository(session).get_by_id(invitation.id) is None


async def test_stored_status_round_trips():
    invitation = _issue(await _tenant())
    await _add(invitation)

    async with SessionLocal() as session:
        stored = await SQLAlchemyTenantInvitationRepository(session).get_by_id(invitation.id)

    assert (stored.status, stored.email, stored.role) == (InvitationStatus.PENDING, "ada@futa.edu.ng", MembershipRole.STUDENT)
    assert stored.is_pending_at(datetime.now(timezone.utc))

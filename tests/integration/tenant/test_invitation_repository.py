from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.tenant.invitation import InvitationStatus, TenantInvitation
from app.domain.tenant.value_objects import MembershipRole, TenantId
from app.infrastructure.db.models.tenant_core import TenantModel
from app.infrastructure.tenant.invitation_repository import (
    SQLAlchemyTenantInvitationRepository,
)


async def _tenant(session) -> str:
    now = datetime.now(timezone.utc)
    tenant_id = str(uuid4())
    session.add(
        TenantModel(id=tenant_id, name="FUTA", slug=f"t-{uuid4().hex[:10]}", status="active", created_at=now, updated_at=now)
    )
    await session.flush()
    return tenant_id


def _issue(tenant_id, email="ada@futa.edu.ng", role=MembershipRole.STUDENT):
    return TenantInvitation.issue(
        tenant_id=TenantId(tenant_id),
        email=email,
        role=role,
        token_hash=uuid4().hex + uuid4().hex,
        invited_by_user_id=None,
    )


async def test_round_trips_and_finds_by_token_and_pending_email(session):
    repo = SQLAlchemyTenantInvitationRepository(session)
    tenant_id = await _tenant(session)
    inv = _issue(tenant_id, role=MembershipRole.LECTURER)

    await repo.add(inv)

    found = await repo.get_by_token_hash(inv.token_hash)
    assert (found.id, found.email, found.role, found.status) == (
        inv.id,
        "ada@futa.edu.ng",
        MembershipRole.LECTURER,
        InvitationStatus.PENDING,
    )
    assert (await repo.get_pending(tenant_id, "ADA@futa.edu.ng ")).id == inv.id
    assert [i.id for i in await repo.list_by_tenant(tenant_id)] == [inv.id]
    assert await repo.get_by_token_hash("unknown") is None


async def test_only_one_pending_invitation_per_email_per_tenant(session):
    repo = SQLAlchemyTenantInvitationRepository(session)
    tenant_id, other_tenant = await _tenant(session), await _tenant(session)
    await repo.add(_issue(tenant_id))
    await repo.add(_issue(other_tenant))  # another tenant is fine

    with pytest.raises(IntegrityError):
        await repo.add(_issue(tenant_id))
    await session.rollback()


async def test_a_revoked_invitation_frees_the_address_for_a_new_one(session):
    repo = SQLAlchemyTenantInvitationRepository(session)
    tenant_id = await _tenant(session)
    first = _issue(tenant_id)
    await repo.add(first)

    first.revoke()
    assert await repo.mark_revoked(first)
    second = _issue(tenant_id)
    await repo.add(second)

    assert (await repo.get_pending(tenant_id, "ada@futa.edu.ng")).id == second.id
    assert [i.id for i in await repo.list_by_tenant(tenant_id, InvitationStatus.REVOKED)] == [first.id]


async def test_transitions_apply_only_while_still_pending(session):
    repo = SQLAlchemyTenantInvitationRepository(session)
    tenant_id = await _tenant(session)
    inv = _issue(tenant_id)
    await repo.add(inv)

    stale = await repo.get_by_id(inv.id)  # a second request's copy
    inv.accept(user_id="u1", user_email="ada@futa.edu.ng", email_verified=True)
    assert await repo.mark_accepted(inv)

    stale.revoke()
    assert not await repo.mark_revoked(stale)
    stored = await repo.get_by_id(inv.id)
    assert (stored.status, stored.accepted_by_user_id) == (InvitationStatus.ACCEPTED, "u1")


async def test_transitions_require_the_matching_domain_state(session):
    repo = SQLAlchemyTenantInvitationRepository(session)
    inv = _issue(await _tenant(session))
    await repo.add(inv)

    with pytest.raises(ValueError):
        await repo.mark_accepted(inv)  # still pending in memory

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.tenant.join_policy import TenantJoinPolicy
from app.domain.tenant.value_objects import MembershipRole, TenantId
from app.infrastructure.db.models.tenant_core import TenantModel
from app.infrastructure.tenant.join_policy_repository import (
    SQLAlchemyTenantJoinPolicyRepository,
)


async def _tenant(session) -> str:
    now = datetime.now(timezone.utc)
    tenant_id = str(uuid4())
    session.add(
        TenantModel(id=tenant_id, name="FUTA", slug=f"t-{uuid4().hex[:10]}", status="active", created_at=now, updated_at=now)
    )
    await session.flush()
    return tenant_id


async def test_no_row_means_join_is_off(session):
    assert await SQLAlchemyTenantJoinPolicyRepository(session).get(await _tenant(session)) is None


async def test_saves_and_replaces_a_policy(session):
    repo = SQLAlchemyTenantJoinPolicyRepository(session)
    tenant_id = await _tenant(session)
    policy = TenantJoinPolicy(tenant_id=TenantId(tenant_id))
    policy.configure(enabled=True, allowed_domains=["futa.edu.ng"], updated_by_user_id=None)
    await repo.save(policy)

    policy.configure(enabled=True, allowed_domains=["futa.edu.ng", "student.futa.edu.ng"], updated_by_user_id=None)
    await repo.save(policy)
    session.expunge_all()

    stored = await repo.get(tenant_id)
    assert (stored.enabled, stored.allowed_domains, stored.default_role) == (
        True,
        ("futa.edu.ng", "student.futa.edu.ng"),
        MembershipRole.STUDENT,
    )
    assert stored.auto_join_role_for("ada@student.futa.edu.ng", email_verified=True) is MembershipRole.STUDENT

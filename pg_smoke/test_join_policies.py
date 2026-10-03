from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.domain.tenant.join_policy import TenantJoinPolicy
from app.domain.tenant.value_objects import MembershipRole, TenantId
from app.infrastructure.tenant.join_policy_repository import (
    SQLAlchemyTenantJoinPolicyRepository,
)
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_join_policy_round_trips_and_follows_its_tenant():
    tenant_id = str(uuid4())
    async with SessionLocal() as session:
        await session.execute(
            text(
                "insert into tenants (id, name, slug, status, created_at, updated_at) "
                "values (:id, 'Join', :slug, 'active', :now, :now)"
            ),
            {"id": tenant_id, "slug": f"join-{uuid4().hex[:10]}", "now": datetime.now(timezone.utc)},
        )
        repo = SQLAlchemyTenantJoinPolicyRepository(session)
        policy = TenantJoinPolicy(tenant_id=TenantId(tenant_id))
        policy.configure(enabled=True, allowed_domains=["futa.edu.ng", "student.futa.edu.ng"], updated_by_user_id=None)
        await repo.save(policy)
        await session.commit()

    async with SessionLocal() as session:
        stored = await SQLAlchemyTenantJoinPolicyRepository(session).get(tenant_id)
        assert stored.allowed_domains == ("futa.edu.ng", "student.futa.edu.ng")
        assert stored.auto_join_role_for("ada@futa.edu.ng", email_verified=True) is MembershipRole.STUDENT

        await session.execute(text("delete from tenants where id = :id"), {"id": tenant_id})
        await session.commit()
        assert await SQLAlchemyTenantJoinPolicyRepository(session).get(tenant_id) is None

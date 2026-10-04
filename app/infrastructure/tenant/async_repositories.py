from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.membership import Membership
from app.domain.tenant.tenant import Tenant
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from app.infrastructure.tenant.mappers import (
    membership_to_domain,
    membership_to_model,
    tenant_to_domain,
    tenant_to_model,
)


class AsyncSqlAlchemyTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.scalars(select(TenantModel).where(TenantModel.slug == slug))
        model = result.first()
        return tenant_to_domain(model) if model is not None else None

    async def get_by_id(self, tenant_id: str) -> Tenant | None:
        model = await self.session.get(TenantModel, tenant_id)
        return tenant_to_domain(model) if model is not None else None

    async def add(self, tenant: Tenant) -> None:
        self.session.add(tenant_to_model(tenant))
        await self.session.flush()


class AsyncSqlAlchemyMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tenant_user(self, tenant_id: str, user_id: str) -> Membership | None:
        result = await self.session.scalars(
            select(MembershipModel).where(
                MembershipModel.tenant_id == tenant_id,
                MembershipModel.user_id == user_id,
            )
        )
        model = result.first()
        return membership_to_domain(model) if model is not None else None

    async def add(self, membership: Membership) -> None:
        self.session.add(membership_to_model(membership))
        await self.session.flush()

    async def save(self, membership: Membership) -> None:
        model = await self.session.get(MembershipModel, membership.id.value)
        if model is None:
            raise ValueError(f"membership {membership.id.value} does not exist")
        model.role = membership.role.value
        model.status = membership.status.value
        model.updated_at = membership.updated_at
        await self.session.flush()

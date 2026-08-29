from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.membership import Membership
from app.domain.tenant.tenant import Tenant
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from app.infrastructure.tenant.mappers import membership_to_domain, tenant_to_domain


class AsyncSqlAlchemyTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.scalars(
            select(TenantModel).where(TenantModel.slug == slug)
        )
        model = result.first()
        return tenant_to_domain(model) if model is not None else None


class AsyncSqlAlchemyMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tenant_user(
        self, tenant_id: str, user_id: str
    ) -> Membership | None:
        result = await self.session.scalars(
            select(MembershipModel).where(
                MembershipModel.tenant_id == tenant_id,
                MembershipModel.user_id == user_id,
            )
        )
        model = result.first()
        return membership_to_domain(model) if model is not None else None

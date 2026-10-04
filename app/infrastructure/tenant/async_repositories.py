from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.errors import MembershipAlreadyExistsError
from app.domain.tenant.membership import Membership
from app.domain.tenant.tenant import Tenant
from app.infrastructure.db.models.tenant_core import MembershipModel, TenantModel
from app.infrastructure.identity.models import UserModel
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

    async def get_by_id(self, membership_id: str) -> Membership | None:
        model = await self.session.get(MembershipModel, membership_id)
        return membership_to_domain(model) if model is not None else None

    async def list_with_emails(self, tenant_id: str, status: str | None = None) -> list[tuple[Membership, str]]:
        statement = (
            select(MembershipModel, UserModel.email)
            .join(UserModel, UserModel.id == MembershipModel.user_id)
            .where(MembershipModel.tenant_id == tenant_id)
            .order_by(MembershipModel.created_at)
        )
        if status is not None:
            statement = statement.where(MembershipModel.status == status)
        rows = await self.session.execute(statement)
        return [(membership_to_domain(model), email) for model, email in rows]

    async def list_active_for_user(self, user_id: str) -> list[tuple[Membership, Tenant]]:
        """The user's active memberships in active tenants, oldest first."""
        rows = await self.session.execute(
            select(MembershipModel, TenantModel)
            .join(TenantModel, TenantModel.id == MembershipModel.tenant_id)
            .where(
                MembershipModel.user_id == user_id,
                MembershipModel.status == "active",
                TenantModel.status == "active",
            )
            .order_by(MembershipModel.created_at)
        )
        return [(membership_to_domain(m), tenant_to_domain(t)) for m, t in rows]

    async def lock_active_owner_ids(self, tenant_id: str) -> list[str]:
        """Lock the tenant's active owner memberships and return their ids.

        Taken before any change that could remove an owner, so two such
        changes in the same tenant run one after the other and the second
        sees the first's result (PostgreSQL re-checks locked rows).
        """
        rows = await self.session.scalars(
            select(MembershipModel.id)
            .where(
                MembershipModel.tenant_id == tenant_id,
                MembershipModel.role == "owner",
                MembershipModel.status == "active",
            )
            .order_by(MembershipModel.id)
            .with_for_update()
        )
        return list(rows)

    async def add(self, membership: Membership) -> None:
        self.session.add(membership_to_model(membership))
        try:
            await self.session.flush()
        except IntegrityError as exc:
            # uq_memberships_tenant_user: a concurrent request got there first.
            raise MembershipAlreadyExistsError("user already has a membership in this tenant") from exc

    async def save(self, membership: Membership) -> None:
        model = await self.session.get(MembershipModel, membership.id.value)
        if model is None:
            raise ValueError(f"membership {membership.id.value} does not exist")
        model.role = membership.role.value
        model.status = membership.status.value
        model.updated_at = membership.updated_at
        await self.session.flush()

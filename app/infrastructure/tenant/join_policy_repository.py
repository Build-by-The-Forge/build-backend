from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.join_policy import TenantJoinPolicy
from app.domain.tenant.value_objects import MembershipRole, TenantId
from app.infrastructure.db.models.tenant_core import TenantJoinPolicyModel


class SQLAlchemyTenantJoinPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: str) -> TenantJoinPolicy | None:
        model = await self._session.get(TenantJoinPolicyModel, tenant_id)
        if model is None:
            return None
        return TenantJoinPolicy(
            tenant_id=TenantId(model.tenant_id),
            enabled=model.enabled,
            allowed_domains=tuple(model.allowed_domains),
            default_role=MembershipRole(model.default_role),
            updated_by_user_id=model.updated_by_user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def save(self, policy: TenantJoinPolicy) -> None:
        model = await self._session.get(TenantJoinPolicyModel, policy.tenant_id.value)
        if model is None:
            model = TenantJoinPolicyModel(tenant_id=policy.tenant_id.value, created_at=policy.created_at)
            self._session.add(model)
        model.enabled = policy.enabled
        model.allowed_domains = list(policy.allowed_domains)
        model.default_role = policy.default_role.value
        model.updated_by_user_id = policy.updated_by_user_id
        model.updated_at = policy.updated_at
        await self._session.flush()

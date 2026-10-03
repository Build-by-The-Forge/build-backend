from typing import Protocol

from app.domain.tenant.join_policy import TenantJoinPolicy


class TenantJoinPolicyRepository(Protocol):
    async def get(self, tenant_id: str) -> TenantJoinPolicy | None:
        """The tenant's policy; None means email-domain join is off."""
        ...

    async def save(self, policy: TenantJoinPolicy) -> None:
        """Create or replace the tenant's policy."""
        ...

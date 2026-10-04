from typing import Protocol

from app.domain.tenant.invitation import InvitationStatus, TenantInvitation


class TenantInvitationRepository(Protocol):
    async def add(self, invitation: TenantInvitation) -> None: ...

    async def get_by_id(self, invitation_id: str) -> TenantInvitation | None: ...

    async def get_by_token_hash(self, token_hash: str) -> TenantInvitation | None: ...

    async def get_pending(self, tenant_id: str, email: str) -> TenantInvitation | None:
        """The pending invitation for this address, if any (at most one)."""
        ...

    async def list_by_tenant(self, tenant_id: str, status: InvitationStatus | None = None) -> list[TenantInvitation]: ...

    async def mark_accepted(self, invitation: TenantInvitation) -> bool:
        """Persist an accepted invitation only if it is still pending.

        Returns False if another request accepted or revoked it first, so two
        concurrent accepts cannot both succeed.
        """
        ...

    async def mark_revoked(self, invitation: TenantInvitation) -> bool:
        """Persist a revocation only if the invitation is still pending."""
        ...

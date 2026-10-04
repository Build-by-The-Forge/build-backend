from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.identity.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.tenant.async_repositories import (
    AsyncSqlAlchemyMembershipRepository,
    AsyncSqlAlchemyTenantRepository,
)
from app.infrastructure.tenant.invitation_repository import (
    SQLAlchemyTenantInvitationRepository,
)
from app.infrastructure.tenant.join_policy_repository import (
    SQLAlchemyTenantJoinPolicyRepository,
)
from app.infrastructure.unit_of_work import UnitOfWork


class TenantMembershipUnitOfWork(UnitOfWork):
    """Tenants, memberships, invitations and users in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.tenants = AsyncSqlAlchemyTenantRepository(session)
        self.memberships = AsyncSqlAlchemyMembershipRepository(session)
        self.invitations = SQLAlchemyTenantInvitationRepository(session)
        self.users = SQLAlchemyUserRepository(session)
        self.join_policies = SQLAlchemyTenantJoinPolicyRepository(session)

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenant.invitation import InvitationStatus, TenantInvitation
from app.domain.tenant.value_objects import MembershipRole, TenantId
from app.infrastructure.db.models.tenant_core import TenantInvitationModel


def invitation_to_domain(model: TenantInvitationModel) -> TenantInvitation:
    return TenantInvitation(
        id=model.id,
        tenant_id=TenantId(model.tenant_id),
        email=model.email,
        role=MembershipRole(model.role),
        token_hash=model.token_hash,
        invited_by_user_id=model.invited_by_user_id,
        expires_at=model.expires_at,
        status=InvitationStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        accepted_at=model.accepted_at,
        accepted_by_user_id=model.accepted_by_user_id,
        revoked_at=model.revoked_at,
    )


def invitation_to_model(invitation: TenantInvitation) -> TenantInvitationModel:
    return TenantInvitationModel(
        id=invitation.id,
        tenant_id=invitation.tenant_id.value,
        email=invitation.email,
        role=invitation.role.value,
        token_hash=invitation.token_hash,
        invited_by_user_id=invitation.invited_by_user_id,
        status=invitation.status.value,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
        accepted_at=invitation.accepted_at,
        accepted_by_user_id=invitation.accepted_by_user_id,
        revoked_at=invitation.revoked_at,
    )


class SQLAlchemyTenantInvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invitation: TenantInvitation) -> None:
        self._session.add(invitation_to_model(invitation))
        await self._session.flush()

    async def _one(self, *conditions: object) -> TenantInvitation | None:
        model = await self._session.scalar(select(TenantInvitationModel).where(*conditions))
        return invitation_to_domain(model) if model is not None else None

    async def get_by_id(self, invitation_id: str) -> TenantInvitation | None:
        return await self._one(TenantInvitationModel.id == invitation_id)

    async def get_by_token_hash(self, token_hash: str) -> TenantInvitation | None:
        return await self._one(TenantInvitationModel.token_hash == token_hash)

    async def get_pending(self, tenant_id: str, email: str) -> TenantInvitation | None:
        return await self._one(
            TenantInvitationModel.tenant_id == tenant_id,
            TenantInvitationModel.email == email.strip().lower(),
            TenantInvitationModel.status == InvitationStatus.PENDING.value,
        )

    async def list_by_tenant(self, tenant_id: str, status: InvitationStatus | None = None) -> list[TenantInvitation]:
        statement = select(TenantInvitationModel).where(TenantInvitationModel.tenant_id == tenant_id)
        if status is not None:
            statement = statement.where(TenantInvitationModel.status == status.value)
        statement = statement.order_by(TenantInvitationModel.created_at.desc())
        return [invitation_to_domain(m) for m in await self._session.scalars(statement)]

    async def _transition_from_pending(self, invitation: TenantInvitation) -> bool:
        # Conditional on the row still being pending: of two concurrent
        # requests only one can move it on.
        result = await self._session.execute(
            update(TenantInvitationModel)
            .where(
                TenantInvitationModel.id == invitation.id,
                TenantInvitationModel.status == InvitationStatus.PENDING.value,
            )
            .values(
                status=invitation.status.value,
                accepted_at=invitation.accepted_at,
                accepted_by_user_id=invitation.accepted_by_user_id,
                revoked_at=invitation.revoked_at,
                updated_at=invitation.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    async def mark_accepted(self, invitation: TenantInvitation) -> bool:
        if invitation.status is not InvitationStatus.ACCEPTED:
            raise ValueError("invitation has not been accepted")
        return await self._transition_from_pending(invitation)

    async def mark_revoked(self, invitation: TenantInvitation) -> bool:
        if invitation.status is not InvitationStatus.REVOKED:
            raise ValueError("invitation has not been revoked")
        return await self._transition_from_pending(invitation)

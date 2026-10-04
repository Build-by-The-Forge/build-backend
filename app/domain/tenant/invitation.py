"""Invitations to join a tenant (M2 design §3.6).

An invitation names an email address and a role. Accepting it is the only
way an invitation leads to a membership, and only for an account whose
*verified* email is the invited address (decision D4). The invitation never
grants anything itself: the resulting membership record is what tenant
authorization reads. Who may invite whom (the role grant hierarchy) is an
application rule, not this entity's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

from app.domain.identity.value_objects import Email
from app.domain.tenant.errors import TenantDomainError
from app.domain.tenant.value_objects import MembershipRole, TenantId

DEFAULT_INVITATION_LIFETIME = timedelta(days=7)


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class InvitationError(TenantDomainError):
    pass


class InvitationNotPendingError(InvitationError):
    pass


class InvitationExpiredError(InvitationError):
    pass


class InvitationEmailMismatchError(InvitationError):
    pass


class InvitationRequiresVerifiedEmailError(InvitationError):
    pass


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@dataclass
class TenantInvitation:
    id: str
    tenant_id: TenantId
    email: str
    role: MembershipRole
    token_hash: str
    invited_by_user_id: str | None
    expires_at: datetime
    status: InvitationStatus = InvitationStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accepted_at: datetime | None = None
    accepted_by_user_id: str | None = None
    revoked_at: datetime | None = None

    @classmethod
    def issue(
        cls,
        *,
        tenant_id: TenantId,
        email: str,
        role: MembershipRole,
        token_hash: str,
        invited_by_user_id: str | None,
        lifetime: timedelta = DEFAULT_INVITATION_LIFETIME,
        now: datetime | None = None,
    ) -> TenantInvitation:
        now = now or datetime.now(timezone.utc)
        return cls(
            id=str(uuid4()),
            tenant_id=tenant_id,
            email=Email(email).value,
            role=MembershipRole(role),
            token_hash=token_hash,
            invited_by_user_id=invited_by_user_id,
            expires_at=now + lifetime,
            created_at=now,
            updated_at=now,
        )

    def is_pending_at(self, now: datetime) -> bool:
        return self.status is InvitationStatus.PENDING and _utc(self.expires_at) > _utc(now)

    def accept(
        self,
        *,
        user_id: str,
        user_email: str,
        email_verified: bool,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        if self.status is not InvitationStatus.PENDING:
            raise InvitationNotPendingError(f"invitation is {self.status.value}")
        if _utc(self.expires_at) <= _utc(now):
            raise InvitationExpiredError("invitation has expired")
        if not email_verified:
            raise InvitationRequiresVerifiedEmailError("verify your email address first")
        if Email(user_email).value != self.email:
            raise InvitationEmailMismatchError("invitation is for a different email address")
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = now
        self.accepted_by_user_id = user_id
        self.updated_at = now

    def revoke(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if self.status is not InvitationStatus.PENDING:
            raise InvitationNotPendingError(f"invitation is {self.status.value}")
        self.status = InvitationStatus.REVOKED
        self.revoked_at = now
        self.updated_at = now

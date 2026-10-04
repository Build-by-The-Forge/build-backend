"""Invite people into a tenant and accept invitations (M2 design 3.6).

* Inviting needs the tenant.member.invite permission (checked by the route)
  and is bounded by the role grant policy: nobody invites to a role they
  could not grant themselves.
* The invitation code goes out by email and is never returned by the API;
  only its hash is stored.
* Accepting needs a signed-in account whose *verified* email is the invited
  address. It never changes an existing active membership: an invitation
  is not a way to raise (or lower) someone's role, that is the
  role-change operation's job. An archived membership is reactivated with
  the invited role.
* The tenant comes from the route (inviting) or the invitation itself
  (accepting), never from the request body.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.application.identity.handlers import hash_token
from app.application.identity.ports.email_sender import EmailMessage, EmailSender
from app.application.identity.ports.security_events import (
    SecurityEvent,
    SecurityEventRecorder,
)
from app.core.exceptions import AppError
from app.core.tenant_context import TenantContext
from app.domain.tenant.invitation import (
    DEFAULT_INVITATION_LIFETIME,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotPendingError,
    InvitationRequiresVerifiedEmailError,
    InvitationStatus,
    TenantInvitation,
)
from app.domain.tenant.membership import Membership
from app.domain.tenant.role_policy import can_grant
from app.domain.tenant.value_objects import MembershipRole, TenantId, UserId

UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[Any]]


@dataclass(frozen=True)
class AcceptedInvitation:
    tenant_id: str
    tenant_slug: str
    membership_id: str
    role: MembershipRole
    reactivated: bool


def invitation_email(tenant_name: str, invitation: TenantInvitation, raw_token: str) -> EmailMessage:
    days = max(int((invitation.expires_at - invitation.created_at).total_seconds() // 86400), 1)
    return EmailMessage(
        to=invitation.email,
        subject=f"You have been invited to {tenant_name} on BUILD",
        body=(
            f"You have been invited to join {tenant_name} on BUILD as {invitation.role.value}.\n\n"
            f"{raw_token}\n\n"
            f"Sign in (or create an account) with this email address, verify it, and use the "
            f"code above to accept. It expires in {days} days and can be used once."
        ),
    )


def _role(value: str) -> MembershipRole:
    try:
        return MembershipRole(value)
    except ValueError:
        raise AppError(f"unknown role: {value!r}", status_code=422) from None


class TenantInvitationService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        email_sender: EmailSender,
        security_events: SecurityEventRecorder,
        lifetime: timedelta = DEFAULT_INVITATION_LIFETIME,
    ) -> None:
        self._uow = uow_factory
        self._email_sender = email_sender
        self._events = security_events
        self._lifetime = lifetime

    async def invite(self, context: TenantContext, email: str, role: str) -> TenantInvitation:
        wanted = _role(role)
        if not can_grant(MembershipRole(context.role), wanted):
            raise AppError("you cannot grant this role", status_code=403)

        raw_token = secrets.token_urlsafe(32)
        replaced: str | None = None
        async with self._uow() as uow:
            try:
                invitation = TenantInvitation.issue(
                    tenant_id=TenantId(context.tenant_id),
                    email=email,
                    role=wanted,
                    token_hash=hash_token(raw_token),
                    invited_by_user_id=context.user_id,
                    lifetime=self._lifetime,
                )
            except ValueError as exc:
                raise AppError(str(exc), status_code=422) from exc

            existing_user = await uow.users.get_by_email(invitation.email)
            if existing_user is not None:
                membership = await uow.memberships.get_by_tenant_user(context.tenant_id, existing_user.id.value)
                if membership is not None and membership.is_active:
                    raise AppError("this person is already a member of the tenant", status_code=409)

            # Re-inviting replaces the outstanding invitation (one pending per address).
            pending = await uow.invitations.get_pending(context.tenant_id, invitation.email)
            if pending is not None:
                if not can_grant(MembershipRole(context.role), pending.role):
                    raise AppError("an invitation you cannot replace is pending", status_code=403)
                pending.revoke()
                await uow.invitations.mark_revoked(pending)
                replaced = pending.id
            await uow.invitations.add(invitation)
            tenant = await uow.tenants.get_by_id(context.tenant_id)

        # Sent only after the invitation is committed, so the code works.
        await self._email_sender.send(invitation_email(tenant.name.value, invitation, raw_token))
        await self._events.record(
            SecurityEvent.INVITATION_CREATED,
            user_id=context.user_id,
            metadata={
                "tenant_id": context.tenant_id,
                "invitation_id": invitation.id,
                "role": invitation.role.value,
                **({"replaced_invitation_id": replaced} if replaced else {}),
            },
        )
        return invitation

    async def list(self, context: TenantContext, status: str | None) -> list[TenantInvitation]:
        try:
            wanted = InvitationStatus(status) if status else None
        except ValueError:
            raise AppError(f"unknown status: {status!r}", status_code=422) from None
        async with self._uow() as uow:
            return await uow.invitations.list_by_tenant(context.tenant_id, wanted)

    async def revoke(self, context: TenantContext, invitation_id: str) -> TenantInvitation:
        async with self._uow() as uow:
            invitation = await uow.invitations.get_by_id(invitation_id)
            # Another tenant's invitation is indistinguishable from a missing one.
            if invitation is None or invitation.tenant_id.value != context.tenant_id:
                raise AppError("invitation not found", status_code=404)
            if not can_grant(MembershipRole(context.role), invitation.role):
                raise AppError("you cannot revoke an invitation for this role", status_code=403)
            try:
                invitation.revoke()
            except InvitationNotPendingError as exc:
                raise AppError(str(exc), status_code=409) from exc
            if not await uow.invitations.mark_revoked(invitation):
                raise AppError("invitation is no longer pending", status_code=409)

        await self._events.record(
            SecurityEvent.INVITATION_REVOKED,
            user_id=context.user_id,
            metadata={"tenant_id": context.tenant_id, "invitation_id": invitation.id},
        )
        return invitation

    async def accept(self, user_id: str, raw_token: str) -> AcceptedInvitation:
        if not raw_token:
            raise AppError("invalid invitation", status_code=422)
        async with self._uow() as uow:
            invitation = await uow.invitations.get_by_token_hash(hash_token(raw_token))
            if invitation is None:
                raise AppError("invalid invitation", status_code=404)
            tenant = await uow.tenants.get_by_id(invitation.tenant_id.value)
            if tenant is None or not tenant.is_active:
                raise AppError("invalid invitation", status_code=404)
            user = await uow.users.get_by_id(user_id)

            try:
                invitation.accept(
                    user_id=user_id,
                    user_email=user.email.value,
                    email_verified=user.email_verified,
                )
            except InvitationRequiresVerifiedEmailError as exc:
                raise AppError("email verification required", status_code=403) from exc
            except InvitationEmailMismatchError as exc:
                raise AppError(str(exc), status_code=403) from exc
            except (InvitationNotPendingError, InvitationExpiredError) as exc:
                raise AppError("invitation is no longer valid", status_code=409) from exc

            membership = await uow.memberships.get_by_tenant_user(tenant.id.value, user_id)
            if membership is not None and membership.is_active:
                raise AppError("you are already a member of this tenant", status_code=409)

            # Conditional on still pending: of two concurrent accepts one wins.
            if not await uow.invitations.mark_accepted(invitation):
                raise AppError("invitation is no longer valid", status_code=409)

            reactivated = membership is not None
            if membership is None:
                membership = Membership.create(tenant_id=tenant.id, user_id=UserId(user_id), role=invitation.role)
                await uow.memberships.add(membership)
            else:
                membership.reactivate()
                membership.change_role(invitation.role)
                await uow.memberships.save(membership)

        await self._events.record(
            SecurityEvent.INVITATION_ACCEPTED,
            user_id=user_id,
            metadata={
                "tenant_id": tenant.id.value,
                "invitation_id": invitation.id,
                "membership_id": membership.id.value,
                "role": invitation.role.value,
                "reactivated": reactivated,
            },
        )
        return AcceptedInvitation(
            tenant_id=tenant.id.value,
            tenant_slug=tenant.slug.value,
            membership_id=membership.id.value,
            role=invitation.role,
            reactivated=reactivated,
        )

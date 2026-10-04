"""List and manage a tenant's members (M2 design 3.6).

Every change runs these checks inside one transaction:

1. The caller's own membership is re-read there; the role resolved at the
   start of the request is not trusted, so a caller demoted or removed a
   moment ago cannot still act on the old role.
2. Nobody changes their own membership here.
3. The caller must outrank the member (role_policy.can_manage) and be able
   to grant any role being given (role_policy.can_grant).
4. The last active owner can never be demoted or removed. The tenant's
   active owner rows are locked first, so two owners demoting each other at
   the same moment cannot leave the tenant without one.

Archiving a membership takes effect on the member's next request, because
tenant access is checked against the membership on every request.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from app.application.identity.ports.security_events import (
    SecurityEvent,
    SecurityEventRecorder,
)
from app.core.authorization import Permission, authorization
from app.core.exceptions import AppError
from app.core.tenant_context import TenantContext
from app.domain.tenant.membership import Membership
from app.domain.tenant.role_policy import can_grant, can_manage
from app.domain.tenant.value_objects import MembershipRole, MembershipStatus

UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[Any]]


@dataclass(frozen=True)
class MemberView:
    membership: Membership
    email: str


def _role(value: str) -> MembershipRole:
    try:
        return MembershipRole(value)
    except ValueError:
        raise AppError(f"unknown role: {value!r}", status_code=422) from None


class TenantMembershipService:
    def __init__(self, uow_factory: UnitOfWorkFactory, security_events: SecurityEventRecorder) -> None:
        self._uow = uow_factory
        self._events = security_events

    async def list(self, context: TenantContext, status: str | None) -> list[MemberView]:
        if status is not None and status not in {s.value for s in MembershipStatus}:
            raise AppError(f"unknown status: {status!r}", status_code=422)
        async with self._uow() as uow:
            rows = await uow.memberships.list_with_emails(context.tenant_id, status)
        return [MemberView(membership, email) for membership, email in rows]

    async def change_role(self, context: TenantContext, membership_id: str, role: str) -> Membership:
        new_role = _role(role)
        async with self._uow() as uow:
            actor, target, owners = await self._prepare(uow, context, membership_id)
            if not target.is_active:
                raise AppError("reactivate the membership before changing its role", status_code=409)
            if not can_grant(actor.role, new_role):
                raise AppError("you cannot grant this role", status_code=403)
            previous = target.role
            if previous is new_role:
                return target
            if previous is MembershipRole.OWNER:
                self._keep_an_owner(target, owners)
            target.change_role(new_role)
            await uow.memberships.save(target)

        await self._record(
            SecurityEvent.MEMBERSHIP_ROLE_CHANGED,
            context,
            target,
            {"from_role": previous.value, "to_role": new_role.value},
        )
        return target

    async def revoke(self, context: TenantContext, membership_id: str) -> Membership:
        async with self._uow() as uow:
            actor, target, owners = await self._prepare(uow, context, membership_id)
            if not target.is_active:
                raise AppError("membership is not active", status_code=409)
            if target.role is MembershipRole.OWNER:
                self._keep_an_owner(target, owners)
            target.archive()
            await uow.memberships.save(target)

        await self._record(SecurityEvent.MEMBERSHIP_REVOKED, context, target, {"role": target.role.value})
        return target

    async def reactivate(self, context: TenantContext, membership_id: str) -> Membership:
        async with self._uow() as uow:
            actor, target, _ = await self._prepare(uow, context, membership_id)
            if target.is_active:
                raise AppError("membership is already active", status_code=409)
            if not can_grant(actor.role, target.role):
                raise AppError("you cannot grant this role", status_code=403)
            target.reactivate()
            await uow.memberships.save(target)

        await self._record(SecurityEvent.MEMBERSHIP_REACTIVATED, context, target, {"role": target.role.value})
        return target

    async def _prepare(self, uow: Any, context: TenantContext, membership_id: str) -> tuple[Membership, Membership, list[str]]:
        # Lock first: everything below is then read under the lock.
        owners = await uow.memberships.lock_active_owner_ids(context.tenant_id)

        actor = await uow.memberships.get_by_id(context.membership_id)
        fresh = (
            TenantContext(context.user_id, context.tenant_id, actor.id.value, actor.role.value)
            if actor is not None and actor.is_active
            else None
        )
        if fresh is None or not authorization.can(fresh, Permission.TENANT_MEMBER_MANAGE):
            raise AppError("permission denied", status_code=403)

        target = await uow.memberships.get_by_id(membership_id)
        # Another tenant's membership is indistinguishable from a missing one.
        if target is None or target.tenant_id.value != context.tenant_id:
            raise AppError("membership not found", status_code=404)
        if target.id.value == actor.id.value:
            raise AppError("you cannot change your own membership", status_code=403)
        if not can_manage(actor.role, target.role):
            raise AppError("you cannot manage this member", status_code=403)
        return actor, target, owners

    @staticmethod
    def _keep_an_owner(target: Membership, active_owner_ids: list[str]) -> None:
        if not set(active_owner_ids) - {target.id.value}:
            raise AppError("a tenant must keep at least one active owner", status_code=409)

    async def _record(self, event: SecurityEvent, context: TenantContext, target: Membership, extra: dict[str, str]) -> None:
        await self._events.record(
            event,
            user_id=context.user_id,
            metadata={
                "tenant_id": context.tenant_id,
                "membership_id": target.id.value,
                "member_user_id": target.user_id.value,
                **extra,
            },
        )

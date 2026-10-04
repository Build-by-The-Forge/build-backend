"""Join a tenant by verified institutional email (decision D5), and manage
the tenant's join policy.

The policy only decides eligibility. Joining creates an ordinary student
membership; from then on the member's authority comes from that membership
and its permissions, never from the email domain. In particular:

* the role is always the policy's role, which can only be student, so no
  domain match ever produces a staff, admin or owner membership;
* an existing active membership is returned unchanged (no promotion, no
  demotion);
* a revoked (archived) membership is never brought back this way: an
  administrator's revocation stands until an administrator reverses it;
* later changes to the policy do not touch existing memberships.
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
from app.core.exceptions import AppError
from app.core.tenant_context import TenantContext
from app.domain.tenant.errors import MembershipAlreadyExistsError
from app.domain.tenant.join_policy import JoinPolicyError, TenantJoinPolicy
from app.domain.tenant.membership import Membership
from app.domain.tenant.value_objects import MembershipRole, TenantId, UserId

UnitOfWorkFactory = Callable[[], AbstractAsyncContextManager[Any]]

NOT_ELIGIBLE = "you are not eligible to join this tenant"


@dataclass(frozen=True)
class JoinResult:
    tenant_id: str
    tenant_slug: str
    membership: Membership
    created: bool


class TenantJoinService:
    def __init__(self, uow_factory: UnitOfWorkFactory, security_events: SecurityEventRecorder) -> None:
        self._uow = uow_factory
        self._events = security_events

    async def join(self, user_id: str, slug: str) -> JoinResult:
        try:
            async with self._uow() as uow:
                tenant = await uow.tenants.get_by_slug(slug.strip().lower())
                if tenant is None or not tenant.is_active:
                    raise AppError("tenant not found", status_code=404)
                existing = await uow.memberships.get_by_tenant_user(tenant.id.value, user_id)
                if existing is not None:
                    return self._existing(tenant, existing)

                user = await uow.users.get_by_id(user_id)
                try:
                    policy = await uow.join_policies.get(tenant.id.value)
                except JoinPolicyError:
                    # A stored policy that breaks the rules (for example edited
                    # by hand to grant a staff role) grants nothing.
                    policy = None
                role = (
                    policy.auto_join_role_for(user.email.value, email_verified=user.email_verified)
                    if policy is not None and user is not None and user.can_authenticate
                    else None
                )
                if role is None:
                    raise AppError(NOT_ELIGIBLE, status_code=403)

                membership = Membership.create(tenant_id=tenant.id, user_id=UserId(user_id), role=role)
                await uow.memberships.add(membership)
        except MembershipAlreadyExistsError:
            # A concurrent join (or invitation) created it first: report that one.
            async with self._uow() as uow:
                tenant = await uow.tenants.get_by_slug(slug.strip().lower())
                existing = await uow.memberships.get_by_tenant_user(tenant.id.value, user_id)
                return self._existing(tenant, existing)

        await self._events.record(
            SecurityEvent.MEMBERSHIP_JOINED_BY_EMAIL_DOMAIN,
            user_id=user_id,
            metadata={
                "tenant_id": tenant.id.value,
                "membership_id": membership.id.value,
                "role": membership.role.value,
            },
        )
        return JoinResult(tenant.id.value, tenant.slug.value, membership, created=True)

    @staticmethod
    def _existing(tenant: Any, membership: Membership) -> JoinResult:
        if not membership.is_active:
            raise AppError(
                "your membership of this tenant was revoked; ask an administrator",
                status_code=403,
            )
        return JoinResult(tenant.id.value, tenant.slug.value, membership, created=False)

    async def get_policy(self, context: TenantContext) -> TenantJoinPolicy:
        async with self._uow() as uow:
            policy = await uow.join_policies.get(context.tenant_id)
        return policy or TenantJoinPolicy(tenant_id=TenantId(context.tenant_id))

    async def set_policy(
        self, context: TenantContext, *, enabled: bool, allowed_domains: list[str], default_role: str
    ) -> TenantJoinPolicy:
        try:
            role = MembershipRole(default_role)
        except ValueError:
            raise AppError(f"unknown role: {default_role!r}", status_code=422) from None
        async with self._uow() as uow:
            policy = await uow.join_policies.get(context.tenant_id) or TenantJoinPolicy(tenant_id=TenantId(context.tenant_id))
            try:
                policy.configure(
                    enabled=enabled,
                    allowed_domains=allowed_domains,
                    default_role=role,
                    updated_by_user_id=context.user_id,
                )
            except JoinPolicyError as exc:
                raise AppError(str(exc), status_code=422) from exc
            await uow.join_policies.save(policy)

        await self._events.record(
            SecurityEvent.TENANT_JOIN_POLICY_UPDATED,
            user_id=context.user_id,
            metadata={
                "tenant_id": context.tenant_id,
                "enabled": policy.enabled,
                "allowed_domains": list(policy.allowed_domains),
            },
        )
        return policy

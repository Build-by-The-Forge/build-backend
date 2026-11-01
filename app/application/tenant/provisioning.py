"""Operator bootstrap: a tenant and its first owner (M2 design 3.5, decision D6).

Idempotent "ensure" semantics: find the tenant by slug or create it, find
the owner by email or create the account, and make sure that account has an
active owner membership in the tenant. Running it again with the same input
changes nothing. It never renames a tenant, never changes an existing
account's password or status, and refuses archived tenants and accounts
that can no longer sign in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.application.identity.ports.password_hasher import PasswordHasher
from app.domain.identity.user import User
from app.domain.identity.value_objects import (
    AccountStatus,
    Email,
    Password,
)
from app.domain.identity.value_objects import UserId as IdentityUserId
from app.domain.repositories.user import UserRepository
from app.domain.tenant.membership import Membership
from app.domain.tenant.tenant import Tenant
from app.domain.tenant.value_objects import (
    MembershipRole,
    MembershipStatus,
    TenantName,
    TenantSlug,
    UserId,
)


class ProvisioningError(Exception):
    """The request cannot be carried out safely; nothing was changed."""


class TenantRepository(Protocol):
    async def get_by_slug(self, slug: str) -> Tenant | None: ...

    async def add(self, tenant: Tenant) -> None: ...


class MembershipRepository(Protocol):
    async def get_by_tenant_user(self, tenant_id: str, user_id: str) -> Membership | None: ...

    async def add(self, membership: Membership) -> None: ...

    async def save(self, membership: Membership) -> None: ...


class MembershipAction(str, Enum):
    CREATED = "created"
    UNCHANGED = "unchanged"
    PROMOTED = "promoted to owner"
    REACTIVATED = "reactivated as owner"


@dataclass
class ProvisioningResult:
    tenant_id: str
    tenant_created: bool
    owner_user_id: str
    owner_created: bool
    membership: MembershipAction
    warnings: list[str] = field(default_factory=list)

    @property
    def owner_granted(self) -> bool:
        return self.membership is not MembershipAction.UNCHANGED


async def provision_tenant(
    *,
    tenants: TenantRepository,
    users: UserRepository,
    memberships: MembershipRepository,
    password_hasher: PasswordHasher,
    name: str,
    slug: str,
    owner_email: str,
    owner_password: str | None,
) -> ProvisioningResult:
    try:
        tenant_name, tenant_slug = TenantName(name), TenantSlug(slug)
        email = Email(owner_email)
    except ValueError as exc:
        raise ProvisioningError(str(exc)) from exc
    warnings: list[str] = []

    tenant = await tenants.get_by_slug(tenant_slug.value)
    tenant_created = tenant is None
    if tenant is None:
        tenant = Tenant.create(name=tenant_name, slug=tenant_slug)
        await tenants.add(tenant)
    elif not tenant.is_active:
        raise ProvisioningError(f"tenant '{tenant_slug.value}' is archived")
    elif tenant.name.value != tenant_name.value:
        warnings.append(f"tenant '{tenant_slug.value}' already exists as '{tenant.name.value}'; not renamed")

    user = await users.get_by_email(email.value)
    owner_created = user is None
    if user is None:
        if not owner_password:
            raise ProvisioningError(f"no account exists for {email.value}; a password is required to create it")
        try:
            password = Password(owner_password)
        except ValueError as exc:
            raise ProvisioningError(str(exc)) from exc
        # The operator vouches for the owner's address, so the account starts
        # active (verified) rather than waiting for a verification email.
        user = await users.save(
            User(
                id=IdentityUserId(""),
                email=email,
                password_hash=password_hasher.hash(password),
                status=AccountStatus.ACTIVE,
            )
        )
    elif not user.can_authenticate:
        raise ProvisioningError(f"account {email.value} is {user.status.value} and cannot become an owner")
    elif not user.email_verified:
        warnings.append(f"{email.value} has not verified their email; tenant access opens once they do")

    membership = await memberships.get_by_tenant_user(tenant.id.value, user.id.value)
    if membership is None:
        await memberships.add(
            Membership.create(
                tenant_id=tenant.id,
                user_id=UserId(user.id.value),
                role=MembershipRole.OWNER,
            )
        )
        action = MembershipAction.CREATED
    elif membership.is_active and membership.role is MembershipRole.OWNER:
        action = MembershipAction.UNCHANGED
    else:
        action = MembershipAction.PROMOTED if membership.status is MembershipStatus.ACTIVE else MembershipAction.REACTIVATED
        membership.reactivate()
        membership.change_role(MembershipRole.OWNER)
        await memberships.save(membership)

    return ProvisioningResult(
        tenant_id=tenant.id.value,
        tenant_created=tenant_created,
        owner_user_id=user.id.value,
        owner_created=owner_created,
        membership=action,
        warnings=warnings,
    )

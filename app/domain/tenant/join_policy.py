"""Per-tenant email-domain join policy (decision D5).

A tenant may let students with a *verified* address on one of its
institutional domains (for example ``futa.edu.ng``) join without an
invitation. Off unless a tenant enables it; never hard-coded to a
university. The policy only answers "is this account eligible, and for
which role"; membership is still created as its own record, and tenant
authorization reads only that record, never the email domain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.identity.value_objects import Email
from app.domain.tenant.errors import TenantDomainError
from app.domain.tenant.value_objects import MembershipRole, TenantId

MAX_ALLOWED_DOMAINS = 20
# Staff roles are granted by invitation only.
AUTO_JOIN_ROLES = frozenset({MembershipRole.STUDENT})

_LABEL = r"(?!-)[a-z0-9-]{1,63}(?<!-)"
_DOMAIN_RE = re.compile(rf"^{_LABEL}(?:\.{_LABEL})+$")


class JoinPolicyError(TenantDomainError):
    pass


def normalise_domain(value: str) -> str:
    domain = value.strip().lower()
    if len(domain) > 253 or not _DOMAIN_RE.match(domain):
        raise JoinPolicyError(f"not a valid email domain: {value!r}")
    return domain


@dataclass
class TenantJoinPolicy:
    tenant_id: TenantId
    enabled: bool = False
    allowed_domains: tuple[str, ...] = ()
    default_role: MembershipRole = MembershipRole.STUDENT
    updated_by_user_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self._validate(self.enabled, self.allowed_domains, self.default_role)

    @staticmethod
    def _validate(enabled: bool, domains: tuple[str, ...], role: MembershipRole) -> None:
        if MembershipRole(role) not in AUTO_JOIN_ROLES:
            raise JoinPolicyError("email-domain join can only grant the student role")
        if len(domains) > MAX_ALLOWED_DOMAINS:
            raise JoinPolicyError(f"at most {MAX_ALLOWED_DOMAINS} domains")
        if enabled and not domains:
            raise JoinPolicyError("an enabled policy needs at least one domain")

    def configure(
        self,
        *,
        enabled: bool,
        allowed_domains: list[str],
        default_role: MembershipRole = MembershipRole.STUDENT,
        updated_by_user_id: str | None,
        now: datetime | None = None,
    ) -> None:
        domains = tuple(dict.fromkeys(normalise_domain(d) for d in allowed_domains))
        role = MembershipRole(default_role)
        self._validate(enabled, domains, role)
        self.enabled = enabled
        self.allowed_domains = domains
        self.default_role = role
        self.updated_by_user_id = updated_by_user_id
        self.updated_at = now or datetime.now(timezone.utc)

    def matches(self, email: str) -> bool:
        """Exact domain match: subdomains must be listed explicitly."""
        domain = Email(email).value.rsplit("@", 1)[1]
        return domain in self.allowed_domains

    def auto_join_role_for(self, email: str, *, email_verified: bool) -> MembershipRole | None:
        """The role an account may join with, or None if it is not eligible."""
        if not (self.enabled and email_verified and self.matches(email)):
            return None
        return self.default_role

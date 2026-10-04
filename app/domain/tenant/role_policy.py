"""Who may grant or manage which tenant role (M2 design 3.6).

owner > admin > faculty_admin > hod > lecturer > student

* A member may grant (invite to, or change someone to) only roles strictly
  below their own; an owner may grant any role, so only an owner can create
  another owner or an admin.
* A member may manage (change the role of, revoke, reactivate) only members
  whose current role is strictly below their own; an owner may manage
  anyone.
* Nobody manages their own membership through these rules, so a role can
  never be raised by its holder and an owner cannot remove themselves by
  accident.

This is a security boundary. Whether the caller holds the tenant permission
to invite or manage at all is checked separately (core.authorization); these
rules then bound *which* roles that permission reaches. Keeping the last
active owner is enforced where memberships change, with the tenant's owner
rows locked.
"""

from __future__ import annotations

from app.domain.tenant.value_objects import MembershipRole

RANK: dict[MembershipRole, int] = {
    MembershipRole.STUDENT: 0,
    MembershipRole.LECTURER: 1,
    MembershipRole.HOD: 2,
    MembershipRole.FACULTY_ADMIN: 3,
    MembershipRole.ADMIN: 4,
    MembershipRole.OWNER: 5,
}


def can_grant(actor: MembershipRole, role: MembershipRole) -> bool:
    if actor is MembershipRole.OWNER:
        return True
    return RANK[role] < RANK[actor]


def can_manage(actor: MembershipRole, target: MembershipRole) -> bool:
    if actor is MembershipRole.OWNER:
        return True
    return RANK[target] < RANK[actor]


def grantable_roles(actor: MembershipRole) -> list[MembershipRole]:
    return [role for role in RANK if can_grant(actor, role)]

import pytest
from app.core.authorization import ROLE_PERMISSIONS, Permission
from app.domain.tenant.role_policy import RANK, can_grant, can_manage, grantable_roles
from app.domain.tenant.value_objects import MembershipRole as R

ALL = list(R)


def test_every_role_has_a_rank():
    assert set(RANK) == set(R)


@pytest.mark.parametrize(
    "actor, expected",
    [
        (R.OWNER, {R.OWNER, R.ADMIN, R.FACULTY_ADMIN, R.HOD, R.LECTURER, R.STUDENT}),
        (R.ADMIN, {R.FACULTY_ADMIN, R.HOD, R.LECTURER, R.STUDENT}),
        (R.FACULTY_ADMIN, {R.HOD, R.LECTURER, R.STUDENT}),
        (R.HOD, {R.LECTURER, R.STUDENT}),
        (R.LECTURER, {R.STUDENT}),
        (R.STUDENT, set()),
    ],
)
def test_roles_grant_only_below_themselves_except_owner(actor, expected):
    assert set(grantable_roles(actor)) == expected


@pytest.mark.parametrize("actor", [r for r in ALL if r is not R.OWNER])
def test_only_an_owner_can_create_an_owner_or_admin(actor):
    assert not can_grant(actor, R.OWNER)
    assert not can_grant(actor, R.ADMIN)


@pytest.mark.parametrize("actor", ALL)
def test_nobody_but_an_owner_grants_their_own_role(actor):
    assert can_grant(actor, actor) is (actor is R.OWNER)


@pytest.mark.parametrize("actor", ALL)
@pytest.mark.parametrize("target", ALL)
def test_members_manage_only_strictly_lower_roles(actor, target):
    expected = actor is R.OWNER or RANK[target] < RANK[actor]
    assert can_manage(actor, target) is expected


def test_membership_permissions_by_role():
    def has(role, permission):
        return permission in ROLE_PERMISSIONS[role]

    for role in ("student", "lecturer"):
        assert not any(
            has(role, p)
            for p in (
                Permission.TENANT_MEMBER_READ,
                Permission.TENANT_MEMBER_INVITE,
                Permission.TENANT_MEMBER_MANAGE,
                Permission.TENANT_SETTINGS_MANAGE,
            )
        )
    for role in ("hod", "faculty_admin"):
        assert has(role, Permission.TENANT_MEMBER_READ) and has(role, Permission.TENANT_MEMBER_INVITE)
        assert not has(role, Permission.TENANT_MEMBER_MANAGE)
        assert not has(role, Permission.TENANT_SETTINGS_MANAGE)
    for role in ("admin", "owner"):
        assert all(
            has(role, p)
            for p in (
                Permission.TENANT_MEMBER_READ,
                Permission.TENANT_MEMBER_INVITE,
                Permission.TENANT_MEMBER_MANAGE,
                Permission.TENANT_SETTINGS_MANAGE,
            )
        )

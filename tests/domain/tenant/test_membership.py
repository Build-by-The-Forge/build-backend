import pytest

from app.domain.tenant.errors import MembershipAlreadyArchivedError
from app.domain.tenant.membership import Membership
from app.domain.tenant.value_objects import (
    MembershipRole,
    MembershipStatus,
    TenantId,
    UserId,
)


def test_membership_belongs_to_tenant_and_user() -> None:
    member = Membership.create(
        tenant_id=TenantId(""),
        user_id=UserId("user-123"),
        role=MembershipRole.STUDENT,
    )

    assert member.role == MembershipRole.STUDENT
    assert member.is_active is True
    assert member.user_id.value == "user-123"


def test_membership_role_validates() -> None:
    with pytest.raises(ValueError):
        MembershipRole("invalid_role")

    member = Membership.create(
        tenant_id=TenantId(""),
        user_id=UserId("u1"),
        role=MembershipRole.LECTURER,
    )
    assert member.role == MembershipRole.LECTURER


def test_membership_create_emits_event() -> None:
    member = Membership.create(
        tenant_id=TenantId(""),
        user_id=UserId("u1"),
        role=MembershipRole.ADMIN,
    )

    events = member.pull_events()
    assert events[0].event_type == "membership.created"
    assert events[0].payload["role"] == "admin"


def test_membership_change_role_and_archive() -> None:
    member = Membership.create(
        tenant_id=TenantId(""),
        user_id=UserId("u1"),
        role=MembershipRole.STUDENT,
    )
    member.pull_events()

    member.change_role(MembershipRole.HOD)
    assert member.role == MembershipRole.HOD

    member.archive()
    assert member.status == MembershipStatus.ARCHIVED

    with pytest.raises(MembershipAlreadyArchivedError):
        member.archive()

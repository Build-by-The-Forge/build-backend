from datetime import datetime, timedelta, timezone

import pytest

from app.domain.tenant.invitation import (
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotPendingError,
    InvitationRequiresVerifiedEmailError,
    InvitationStatus,
    TenantInvitation,
)
from app.domain.tenant.value_objects import MembershipRole, TenantId

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def invitation(**overrides):
    params = {
        "tenant_id": TenantId("t1"),
        "email": "  Ada@FUTA.edu.ng ",
        "role": MembershipRole.LECTURER,
        "token_hash": "h" * 64,
        "invited_by_user_id": "owner-1",
        "now": NOW,
    }
    params.update(overrides)
    return TenantInvitation.issue(**params)


def accept(inv, *, email="ada@futa.edu.ng", verified=True, now=NOW):
    inv.accept(user_id="u1", user_email=email, email_verified=verified, now=now)


def test_issue_normalises_the_email_and_starts_pending_for_seven_days():
    inv = invitation()

    assert inv.email == "ada@futa.edu.ng"
    assert inv.status is InvitationStatus.PENDING
    assert inv.expires_at == NOW + timedelta(days=7)
    assert inv.is_pending_at(NOW)
    assert not inv.is_pending_at(NOW + timedelta(days=7))


def test_issue_rejects_invalid_emails_and_roles():
    with pytest.raises(ValueError):
        invitation(email="not-an-email")
    with pytest.raises(ValueError):
        invitation(role="superuser")


def test_a_verified_account_with_the_invited_email_can_accept():
    inv = invitation()

    accept(inv, email="ADA@futa.edu.ng")

    assert inv.status is InvitationStatus.ACCEPTED
    assert (inv.accepted_by_user_id, inv.accepted_at) == ("u1", NOW)


def test_an_unverified_account_cannot_accept():
    inv = invitation()

    with pytest.raises(InvitationRequiresVerifiedEmailError):
        accept(inv, verified=False)
    assert inv.status is InvitationStatus.PENDING


def test_a_different_email_cannot_accept():
    inv = invitation()

    with pytest.raises(InvitationEmailMismatchError):
        accept(inv, email="mallory@futa.edu.ng")
    assert inv.status is InvitationStatus.PENDING


def test_an_expired_invitation_cannot_be_accepted():
    inv = invitation()

    with pytest.raises(InvitationExpiredError):
        accept(inv, now=NOW + timedelta(days=7))


def test_an_invitation_is_used_at_most_once():
    inv = invitation()
    accept(inv)

    with pytest.raises(InvitationNotPendingError):
        accept(inv)
    with pytest.raises(InvitationNotPendingError):
        inv.revoke(NOW)


def test_a_revoked_invitation_cannot_be_accepted():
    inv = invitation()
    inv.revoke(NOW)

    assert inv.status is InvitationStatus.REVOKED
    with pytest.raises(InvitationNotPendingError):
        accept(inv)

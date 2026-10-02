from datetime import datetime, timedelta, timezone

import pytest

from app.domain.identity.user import Session, User
from app.domain.identity.value_objects import (
    AccountStatus,
    Email,
    PasswordHash,
    SessionId,
    UserId,
)


def user(**kwargs) -> User:
    return User(id=UserId(""), email=Email("a@example.com"), password_hash=PasswordHash("h"), **kwargs)


def test_new_users_start_unverified():
    assert user().status is AccountStatus.PENDING_VERIFICATION


@pytest.mark.parametrize(
    "status,allowed",
    [
        (AccountStatus.ACTIVE, True),
        (AccountStatus.PENDING_VERIFICATION, True),
        (AccountStatus.LOCKED, False),
        (AccountStatus.DISABLED, False),
        (AccountStatus.DELETED, False),
    ],
)
def test_can_authenticate_by_status(status, allowed):
    assert user(status=status).can_authenticate is allowed


def test_deactivated_user_cannot_authenticate_even_if_active_status():
    assert not user(status=AccountStatus.ACTIVE, is_active=False).can_authenticate


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def session(**kwargs) -> Session:
    return Session(id=SessionId("s"), user_id=UserId("u"), **kwargs)


@pytest.mark.parametrize(
    "kwargs,active",
    [
        ({}, True),
        ({"expires_at": NOW + timedelta(seconds=1)}, True),
        ({"expires_at": NOW - timedelta(seconds=1)}, False),
        ({"expires_at": NOW}, False),
        ({"expires_at": (NOW + timedelta(hours=1)).replace(tzinfo=None)}, True),  # naive (SQLite)
        ({"expires_at": (NOW - timedelta(hours=1)).replace(tzinfo=None)}, False),
        ({"revoked_at": NOW - timedelta(minutes=1)}, False),
    ],
)
def test_session_activity(kwargs, active):
    assert session(**kwargs).is_active_at(NOW) is active

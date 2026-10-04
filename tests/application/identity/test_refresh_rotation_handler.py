from datetime import datetime, timedelta, timezone

import pytest

from app.application.identity.commands import RefreshSessionCommand
from app.application.identity.handlers import (
    RefreshSessionHandler,
    RefreshTokenReuseError,
    hash_token,
    refresh_token_expiry,
)
from app.domain.identity.user import Session, User
from app.domain.identity.value_objects import (
    AccountStatus,
    Email,
    PasswordHash,
    SessionId,
    UserId,
)
from app.domain.repositories.refresh_token import StoredRefreshToken

NOW = datetime.now(timezone.utc)


class Sessions:
    def __init__(self, session):
        self.session = session

    async def get_by_id(self, session_id):
        return self.session

    async def save(self, session):
        return session


class Users:
    async def get_by_id(self, user_id):
        return User(
            id=UserId(user_id),
            email=Email("a@example.com"),
            password_hash=PasswordHash("h"),
            status=AccountStatus.ACTIVE,
        )


class LosingRaceTokens:
    """The token looks current, but another request rotates it first."""

    def __init__(self):
        self.added = []

    async def get_by_hash(self, token_hash):
        return StoredRefreshToken("t1", "s1", NOW + timedelta(days=1), None, None)

    async def consume(self, token_id):
        return False

    async def add(self, *args):
        self.added.append(args)


async def test_losing_a_concurrent_rotation_counts_as_reuse():
    tokens = LosingRaceTokens()
    session = Session(id=SessionId("s1"), user_id=UserId("u1"), expires_at=NOW + timedelta(days=1))
    handler = RefreshSessionHandler(Sessions(session), tokens, Users())

    with pytest.raises(RefreshTokenReuseError) as exc:
        await handler.handle(RefreshSessionCommand(refresh_token="raw"))

    assert exc.value.session_id == "s1"
    assert tokens.added == []  # no replacement issued


def test_refresh_expiry_is_the_idle_window_capped_by_the_session():
    long_session = Session(id=SessionId("s"), user_id=UserId("u"), expires_at=NOW + timedelta(days=30))
    short_session = Session(id=SessionId("s"), user_id=UserId("u"), expires_at=NOW + timedelta(days=3))

    assert refresh_token_expiry(long_session, timedelta(days=14), NOW) == NOW + timedelta(days=14)
    assert refresh_token_expiry(short_session, timedelta(days=14), NOW) == NOW + timedelta(days=3)


def test_hash_token_is_deterministic_sha256():
    assert hash_token("abc") == hash_token("abc")
    assert len(hash_token("abc")) == 64

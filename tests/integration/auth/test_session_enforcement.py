from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.infrastructure.identity.models import SessionModel, UserModel, UserStatus
from app.infrastructure.security.jwt_token_service import JWTTokenService

PASSWORD = "StrongPass123!"


def _db(client, fn):
    """Run an async DB function on the app's event loop (same engine as the API)."""

    async def run():
        async with SessionLocal() as db:
            result = await fn(db)
            await db.commit()
            return result

    return client.portal.call(run)


def _register(client):
    email = f"user-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    return email, user_id


def _login(client, email):
    return client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})


def _whoami(client, token):
    return client.get("/identity/whoami", headers={"Authorization": f"Bearer {token}"})


def _set_user(client, user_id, **values):
    _db(client, lambda db: db.execute(update(UserModel).where(UserModel.id == user_id).values(**values)))


def _set_session(client, session_id, **values):
    _db(client, lambda db: db.execute(update(SessionModel).where(SessionModel.id == session_id).values(**values)))


def test_unverified_account_can_sign_in_and_use_its_token(client):
    email, _ = _register(client)

    login = _login(client, email)

    assert login.status_code == 200
    assert _whoami(client, login.json()["data"]["access_token"]).status_code == 200


def test_login_sets_an_absolute_session_expiry(client):
    email, _ = _register(client)
    session_id = _login(client, email).json()["data"]["session_id"]

    expires_at = _db(
        client,
        lambda db: db.scalar(select(SessionModel.expires_at).where(SessionModel.id == session_id)),
    )
    expires_at = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at

    assert timedelta(days=29) < expires_at - datetime.now(timezone.utc) <= timedelta(days=30)


@pytest.mark.parametrize("status", [UserStatus.LOCKED, UserStatus.DISABLED, UserStatus.DELETED])
def test_login_is_refused_for_blocked_statuses(client, status):
    email, user_id = _register(client)
    _set_user(client, user_id, status=status)

    resp = _login(client, email)

    assert resp.status_code == 403
    assert resp.json()["meta"]["error"] == "account is not active"


def test_login_is_refused_for_deactivated_accounts(client):
    email, user_id = _register(client)
    _set_user(client, user_id, is_active=False)

    assert _login(client, email).status_code == 403


def test_blocked_account_with_wrong_password_still_looks_like_bad_credentials(client):
    email, user_id = _register(client)
    _set_user(client, user_id, status=UserStatus.DISABLED)

    resp = client.post("/identity/authenticate", json={"email": email, "password": "WrongPass12345!"})

    assert resp.status_code == 401


def test_existing_token_stops_working_when_the_account_is_disabled(client):
    email, user_id = _register(client)
    token = _login(client, email).json()["data"]["access_token"]
    assert _whoami(client, token).status_code == 200

    _set_user(client, user_id, status=UserStatus.DISABLED)

    assert _whoami(client, token).status_code == 401


def test_existing_token_stops_working_when_the_session_is_revoked(client):
    email, _ = _register(client)
    data = _login(client, email).json()["data"]
    assert _whoami(client, data["access_token"]).status_code == 200

    client.post("/identity/logout", headers={"Authorization": f"Bearer {data['access_token']}"})

    assert _whoami(client, data["access_token"]).status_code == 401


def test_existing_token_stops_working_when_the_session_expires(client):
    email, _ = _register(client)
    data = _login(client, email).json()["data"]

    _set_session(client, data["session_id"], expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))

    assert _whoami(client, data["access_token"]).status_code == 401


def test_token_pairing_a_user_with_someone_elses_session_is_rejected(client):
    email_a, user_a = _register(client)
    email_b, _ = _register(client)
    session_b = _login(client, email_b).json()["data"]["session_id"]

    forged = JWTTokenService().issue_access_token(user_a, session_b)

    assert _whoami(client, forged).status_code == 401


def test_token_for_an_unknown_session_is_rejected(client):
    _, user_id = _register(client)

    token = JWTTokenService().issue_access_token(user_id, str(uuid4()))

    assert _whoami(client, token).status_code == 401

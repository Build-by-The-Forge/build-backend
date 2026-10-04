import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.infrastructure.identity.models import RefreshTokenModel, UserModel, UserStatus

PASSWORD = "StrongPass123!"


def _db(client, fn):
    async def run():
        async with SessionLocal() as db:
            result = await fn(db)
            await db.commit()
            return result

    return client.portal.call(run)


def _login(client):
    email = f"user-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    data = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]
    return user_id, email, data


def _refresh(client, token):
    return client.post("/identity/refresh", json={"refresh_token": token})


def _whoami(client, access_token):
    return client.get("/identity/whoami", headers={"Authorization": f"Bearer {access_token}"})


def test_refresh_rotates_the_token_pair(client):
    _, _, first = _login(client)

    resp = _refresh(client, first["refresh_token"])

    assert resp.status_code == 200
    second = resp.json()["data"]
    assert second["session_id"] == first["session_id"]
    assert second["refresh_token"] != first["refresh_token"]
    assert second["expires_in"] == 900
    assert _whoami(client, second["access_token"]).status_code == 200
    assert _refresh(client, second["refresh_token"]).status_code == 200


def test_reusing_a_rotated_refresh_token_revokes_the_whole_session(client):
    _, _, first = _login(client)
    second = _refresh(client, first["refresh_token"]).json()["data"]

    reuse = _refresh(client, first["refresh_token"])

    assert reuse.status_code == 401
    # The legitimate holder's newer tokens die with the session.
    assert _refresh(client, second["refresh_token"]).status_code == 401
    assert _whoami(client, second["access_token"]).status_code == 401


def test_refresh_tokens_are_stored_only_as_sha256(client):
    _, _, data = _login(client)
    raw = data["refresh_token"]

    stored = _db(client, lambda db: db.scalars(select(RefreshTokenModel.token_hash)))
    stored = set(stored)

    assert raw not in stored
    assert hashlib.sha256(raw.encode()).hexdigest() in stored


def test_unknown_or_empty_refresh_tokens_are_rejected(client):
    for token in ("", "not-a-real-token", f"refresh:{uuid4()}"):
        assert _refresh(client, token).status_code == 401


def test_refresh_fails_after_logout(client):
    _, _, data = _login(client)

    client.post("/identity/logout", headers={"Authorization": f"Bearer {data['access_token']}"})

    assert _refresh(client, data["refresh_token"]).status_code == 401


def test_refresh_fails_once_the_account_is_disabled(client):
    user_id, _, data = _login(client)
    _db(client, lambda db: db.execute(update(UserModel).where(UserModel.id == user_id).values(status=UserStatus.DISABLED)))

    assert _refresh(client, data["refresh_token"]).status_code == 401


def test_expired_refresh_token_is_rejected(client):
    _, _, data = _login(client)
    token_hash = hashlib.sha256(data["refresh_token"].encode()).hexdigest()
    _db(
        client,
        lambda db: db.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        ),
    )

    assert _refresh(client, data["refresh_token"]).status_code == 401


def test_logout_requires_authentication(client):
    _, _, data = _login(client)

    resp = client.post("/identity/logout", json={"session_id": data["session_id"]})

    assert resp.status_code == 401
    assert _whoami(client, data["access_token"]).status_code == 200


def test_logout_ends_only_the_callers_session(client):
    _, _, mine = _login(client)
    _, _, other = _login(client)

    client.post("/identity/logout", headers={"Authorization": f"Bearer {mine['access_token']}"})

    assert _whoami(client, mine["access_token"]).status_code == 401
    assert _whoami(client, other["access_token"]).status_code == 200


def test_logout_all_ends_every_session_of_the_user(client):
    _, email, first = _login(client)
    second = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]

    resp = client.post("/identity/logout-all", headers={"Authorization": f"Bearer {first['access_token']}"})

    assert resp.status_code == 200
    assert resp.json()["data"]["revoked_sessions"] == 2
    for session in (first, second):
        assert _whoami(client, session["access_token"]).status_code == 401
        assert _refresh(client, session["refresh_token"]).status_code == 401

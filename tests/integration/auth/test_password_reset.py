import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update

from app.api import identity as identity_api
from app.db.session import SessionLocal
from app.infrastructure.identity.models import (
    PasswordResetTokenModel,
    UserModel,
    UserStatus,
)

PASSWORD = "StrongPass123!"
NEW_PASSWORD = "BrandNew-Passphrase-42"
GENERIC = "If an account exists for this email, a reset code has been sent."


def _db(client, fn):
    async def run():
        async with SessionLocal() as db:
            result = await fn(db)
            await db.commit()
            return result

    return client.portal.call(run)


def _outbox():
    return identity_api.service.email_sender


def _register(client):
    email = f"user-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    return email, user_id


def _forgot(client, email):
    return client.post("/identity/forgot-password", json={"email": email})


def _code_for(email):
    message = _outbox().latest_to(email)
    assert message is not None
    return message.body.split("\n\n")[1]


def _reset(client, token, password=NEW_PASSWORD):
    return client.post("/identity/reset-password", json={"token": token, "password": password})


def _login(client, email, password):
    return client.post("/identity/authenticate", json={"email": email, "password": password})


def test_reset_code_is_delivered_by_email_and_never_returned(client):
    email, _ = _register(client)

    resp = _forgot(client, email)

    assert resp.status_code == 200
    assert resp.json()["data"] == {}
    assert resp.json()["meta"]["message"] == GENERIC
    code = _code_for(email)
    assert code not in resp.text
    assert len(code) >= 43  # 256 bits, url-safe base64


def test_unknown_email_gets_the_same_response_and_no_email(client):
    email = f"nobody-{uuid4().hex}@example.com"

    resp = _forgot(client, email)

    assert resp.status_code == 200
    assert resp.json()["data"] == {}
    assert resp.json()["meta"]["message"] == GENERIC
    assert _outbox().latest_to(email) is None


def test_blocked_account_gets_the_same_response_and_no_email(client):
    email, user_id = _register(client)
    _db(client, lambda db: db.execute(update(UserModel).where(UserModel.id == user_id).values(status=UserStatus.DISABLED)))

    resp = _forgot(client, email)

    assert resp.json()["meta"]["message"] == GENERIC
    assert _outbox().latest_to(email) is None


def test_reset_code_is_stored_only_as_sha256(client):
    email, user_id = _register(client)
    _forgot(client, email)
    code = _code_for(email)

    hashes = set(
        _db(client, lambda db: db.scalars(select(PasswordResetTokenModel.token_hash).where(PasswordResetTokenModel.user_id == user_id)))
    )

    assert code not in hashes
    assert hashlib.sha256(code.encode()).hexdigest() in hashes


def test_reset_code_works_once(client):
    email, _ = _register(client)
    _forgot(client, email)
    code = _code_for(email)

    assert _reset(client, code).status_code == 200
    assert _login(client, email, NEW_PASSWORD).status_code == 200
    assert _login(client, email, PASSWORD).status_code == 401
    assert _reset(client, code, "Another-Passphrase-77").status_code == 401


def test_requesting_a_new_code_invalidates_the_previous_one(client):
    email, _ = _register(client)
    _forgot(client, email)
    first = _code_for(email)
    _forgot(client, email)
    second = _code_for(email)

    assert first != second
    assert _reset(client, first).status_code == 401
    assert _reset(client, second).status_code == 200


def test_expired_reset_code_is_rejected(client):
    email, user_id = _register(client)
    _forgot(client, email)
    code = _code_for(email)
    _db(
        client,
        lambda db: db.execute(
            update(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        ),
    )

    assert _reset(client, code).status_code == 401
    assert _login(client, email, PASSWORD).status_code == 200


def test_reset_code_expires_after_the_configured_lifetime(client):
    email, user_id = _register(client)
    _forgot(client, email)

    expires_at = _db(
        client,
        lambda db: db.scalar(select(PasswordResetTokenModel.expires_at).where(PasswordResetTokenModel.user_id == user_id)),
    )
    expires_at = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at

    assert timedelta(minutes=59) < expires_at - datetime.now(timezone.utc) <= timedelta(hours=1)


def test_reset_rejects_garbage_and_weak_passwords(client):
    email, _ = _register(client)
    _forgot(client, email)

    assert _reset(client, "").status_code == 422
    assert _reset(client, "not-a-real-code").status_code == 401
    assert _reset(client, _code_for(email), "short").status_code == 422

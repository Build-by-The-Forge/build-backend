import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.api import identity as identity_api
from app.db.session import SessionLocal
from app.infrastructure.identity.models import (
    UserModel,
    UserStatus,
    VerificationTokenModel,
)

PASSWORD = "StrongPass123!"
SUBJECT = "Verify your BUILD email address"
GENERIC = "If this email needs verification, a new code has been sent."


def _db(client, fn):
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


def _code_for(email):
    message = identity_api.service.email_sender.latest_to(email, SUBJECT)
    return None if message is None else message.body.split("\n\n")[1]


def _verify(client, token):
    return client.post("/identity/verify-email", json={"token": token})


def _resend(client, email):
    return client.post("/identity/resend-verification", json={"email": email})


def _user(client, user_id):
    return _db(client, lambda db: db.get(UserModel, user_id))


def _set_status(client, user_id, status):
    _db(client, lambda db: db.execute(update(UserModel).where(UserModel.id == user_id).values(status=status)))


def test_registration_sends_a_code_and_verifying_activates_the_account(client):
    email, user_id = _register(client)
    code = _code_for(email)
    assert code is not None and len(code) >= 43
    assert _user(client, user_id).status == UserStatus.PENDING_VERIFICATION

    resp = _verify(client, code)

    assert resp.status_code == 200
    assert resp.json()["data"] == {"email_verified": True}
    user = _user(client, user_id)
    assert user.status == UserStatus.ACTIVE
    assert user.is_verified is True


def test_registration_response_does_not_contain_the_code(client):
    email = f"user-{uuid4().hex}@example.com"
    resp = client.post("/identity/users", json={"email": email, "password": PASSWORD})

    assert _code_for(email) not in resp.text


def test_code_is_stored_only_as_sha256(client):
    email, user_id = _register(client)
    code = _code_for(email)

    hashes = set(
        _db(client, lambda db: db.scalars(select(VerificationTokenModel.token_hash).where(VerificationTokenModel.user_id == user_id)))
    )

    assert code not in hashes
    assert hashlib.sha256(code.encode()).hexdigest() in hashes


def test_code_works_once(client):
    email, _ = _register(client)
    code = _code_for(email)

    assert _verify(client, code).status_code == 200
    assert _verify(client, code).status_code == 401


def test_expired_code_is_rejected(client):
    email, user_id = _register(client)
    code = _code_for(email)
    _db(
        client,
        lambda db: db.execute(
            update(VerificationTokenModel)
            .where(VerificationTokenModel.user_id == user_id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        ),
    )

    assert _verify(client, code).status_code == 401
    assert _user(client, user_id).status == UserStatus.PENDING_VERIFICATION


def test_code_lifetime_is_24_hours(client):
    _, user_id = _register(client)

    expires_at = _db(
        client,
        lambda db: db.scalar(select(VerificationTokenModel.expires_at).where(VerificationTokenModel.user_id == user_id)),
    )
    expires_at = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at

    assert timedelta(hours=23, minutes=59) < expires_at - datetime.now(timezone.utc) <= timedelta(hours=24)


def test_resending_invalidates_the_previous_code(client):
    email, _ = _register(client)
    first = _code_for(email)

    resp = _resend(client, email)
    second = _code_for(email)

    assert resp.json()["meta"]["message"] == GENERIC
    assert first != second
    assert _verify(client, first).status_code == 401
    assert _verify(client, second).status_code == 200


def test_unknown_email_gets_the_same_response_and_no_email(client):
    email = f"nobody-{uuid4().hex}@example.com"

    resp = _resend(client, email)

    assert resp.status_code == 200
    assert resp.json()["data"] == {}
    assert resp.json()["meta"]["message"] == GENERIC
    assert _code_for(email) is None


def test_already_verified_account_gets_the_same_response_and_no_new_code(client):
    email, user_id = _register(client)
    code = _code_for(email)
    _verify(client, code)

    resp = _resend(client, email)

    assert resp.json()["meta"]["message"] == GENERIC
    assert _code_for(email) == code  # nothing new was sent
    assert _user(client, user_id).status == UserStatus.ACTIVE


@pytest.mark.parametrize("status", [UserStatus.LOCKED, UserStatus.DISABLED, UserStatus.DELETED])
def test_blocked_account_cannot_verify_its_way_back(client, status):
    email, user_id = _register(client)
    code = _code_for(email)
    _set_status(client, user_id, status)

    assert _verify(client, code).status_code == 401
    assert _user(client, user_id).status == status

    _resend(client, email)
    assert _code_for(email) == code  # no new code for a blocked account


def test_garbage_codes_are_rejected(client):
    assert _verify(client, "").status_code == 422
    assert _verify(client, "not-a-real-code").status_code == 401


def test_verification_survives_login_and_logout(client):
    email, user_id = _register(client)
    _verify(client, _code_for(email))

    session = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]
    client.post("/identity/logout", headers={"Authorization": f"Bearer {session['access_token']}"})
    client.post("/identity/authenticate", json={"email": email, "password": PASSWORD})

    assert _user(client, user_id).status == UserStatus.ACTIVE

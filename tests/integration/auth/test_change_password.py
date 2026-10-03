from uuid import uuid4

from sqlalchemy import select

from app.api import identity as identity_api
from app.db.session import SessionLocal
from app.infrastructure.identity.models import PasswordResetTokenModel

PASSWORD = "StrongPass123!"
NEW_PASSWORD = "BrandNew-Passphrase-42"


def _signed_in(client, sessions=1):
    email = f"user-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    logins = [_login(client, email, PASSWORD).json()["data"] for _ in range(sessions)]
    return email, user_id, logins


def _login(client, email, password):
    return client.post("/identity/authenticate", json={"email": email, "password": password})


def _change(client, access_token, **body):
    payload = {"current_password": PASSWORD, "new_password": NEW_PASSWORD, **body}
    return client.post(
        "/identity/change-password",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )


def _whoami(client, access_token):
    return client.get("/identity/whoami", headers={"Authorization": f"Bearer {access_token}"})


def _refresh(client, token):
    return client.post("/identity/refresh", json={"refresh_token": token})


def test_change_password_requires_authentication(client):
    resp = client.post(
        "/identity/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert resp.status_code == 401


def test_change_password_swaps_the_password_and_ends_other_sessions(client):
    email, _, (mine, other) = _signed_in(client, sessions=2)

    resp = _change(client, mine["access_token"])

    assert resp.status_code == 200
    assert resp.json()["data"]["revoked_sessions"] == 1
    assert _login(client, email, PASSWORD).status_code == 401
    assert _login(client, email, NEW_PASSWORD).status_code == 200
    # The caller stays signed in; every other session is gone.
    assert _whoami(client, mine["access_token"]).status_code == 200
    assert _refresh(client, mine["refresh_token"]).status_code == 200
    assert _whoami(client, other["access_token"]).status_code == 401
    assert _refresh(client, other["refresh_token"]).status_code == 401


def test_other_sessions_can_be_kept_on_request(client):
    _, _, (mine, other) = _signed_in(client, sessions=2)

    resp = _change(client, mine["access_token"], revoke_other_sessions=False)

    assert resp.status_code == 200
    assert resp.json()["data"]["revoked_sessions"] == 0
    assert _whoami(client, other["access_token"]).status_code == 200


def test_wrong_current_password_is_refused_without_a_401(client):
    email, _, (mine,) = _signed_in(client)

    for wrong in ("WrongPass12345!", "short", "x" * 500):
        resp = _change(client, mine["access_token"], current_password=wrong)
        assert resp.status_code == 400
        assert resp.json()["meta"]["error"] == "current password is incorrect"

    assert _login(client, email, PASSWORD).status_code == 200
    assert _whoami(client, mine["access_token"]).status_code == 200


def test_new_password_must_be_valid_and_different(client):
    _, _, (mine,) = _signed_in(client)

    assert _change(client, mine["access_token"], new_password="short").status_code == 422
    assert _change(client, mine["access_token"], new_password=PASSWORD).status_code == 422


def test_malformed_payload_is_rejected(client):
    _, _, (mine,) = _signed_in(client)

    assert _change(client, mine["access_token"], revoke_other_sessions="no").status_code == 422
    assert _change(client, mine["access_token"], new_password=123).status_code == 422


def test_change_password_cancels_outstanding_reset_codes(client):
    email, user_id, (mine,) = _signed_in(client)
    client.post("/identity/forgot-password", json={"email": email})
    code = identity_api.service.email_sender.latest_to(email, "Reset your BUILD password").body.split("\n\n")[1]

    assert _change(client, mine["access_token"]).status_code == 200

    reset = client.post("/identity/reset-password", json={"token": code, "password": "Third-Passphrase-99"})
    assert reset.status_code == 401

    async def outstanding():
        async with SessionLocal() as db:
            return list(
                await db.scalars(
                    select(PasswordResetTokenModel.id).where(
                        PasswordResetTokenModel.user_id == user_id,
                        PasswordResetTokenModel.consumed_at.is_(None),
                    )
                )
            )

    assert client.portal.call(outstanding) == []

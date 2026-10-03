from uuid import uuid4

from app.api import identity as identity_api

PASSWORD = "StrongPass123!"
WRONG = "WrongPass12345!"
RESET_SUBJECT = "Reset your BUILD password"


def _register(client):
    email = f"rl-{uuid4().hex}@example.com"
    client.post("/identity/users", json={"email": email, "password": PASSWORD})
    return email


def _login(client, email, password):
    return client.post("/identity/authenticate", json={"email": email, "password": password})


def _assert_429(resp):
    assert resp.status_code == 429
    assert resp.json()["meta"]["error"] == "too many requests"
    assert int(resp.headers["Retry-After"]) > 0


def test_repeated_wrong_passwords_lock_sign_in_even_with_the_right_password(client):
    email = _register(client)

    for _ in range(5):
        assert _login(client, email, WRONG).status_code == 401

    _assert_429(_login(client, email, WRONG))
    _assert_429(_login(client, email, PASSWORD))


def test_unknown_emails_lock_exactly_like_real_ones(client):
    real, ghost = _register(client), f"ghost-{uuid4().hex}@example.com"

    for email in (real, ghost):
        codes = [_login(client, email, WRONG).status_code for _ in range(6)]
        assert codes == [401] * 5 + [429]


def test_a_lock_on_one_account_leaves_other_accounts_alone(client):
    victim, bystander = _register(client), _register(client)
    for _ in range(5):
        _login(client, victim, WRONG)

    assert _login(client, bystander, PASSWORD).status_code == 200


def test_successful_sign_in_resets_the_failure_count(client):
    email = _register(client)
    for _ in range(4):
        _login(client, email, WRONG)

    assert _login(client, email, PASSWORD).status_code == 200
    for _ in range(4):
        assert _login(client, email, WRONG).status_code == 401
    assert _login(client, email, PASSWORD).status_code == 200


def test_blocked_account_status_is_not_a_failure(client):
    """A correct password for a disabled account (403) does not count."""
    from tests.integration.auth.test_session_enforcement import _set_user
    from app.infrastructure.identity.models import UserStatus

    email = _register(client)
    user_id = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]["user_id"]
    _set_user(client, user_id, status=UserStatus.DISABLED)

    assert [_login(client, email, PASSWORD).status_code for _ in range(7)] == [403] * 7


def test_password_reset_lifts_a_sign_in_lock(client):
    email = _register(client)
    for _ in range(5):
        _login(client, email, WRONG)
    _assert_429(_login(client, email, PASSWORD))

    client.post("/identity/forgot-password", json={"email": email})
    code = identity_api.service.email_sender.latest_to(email, RESET_SUBJECT).body.split("\n\n")[1]
    new_password = "BrandNew-Passphrase-42"
    assert client.post("/identity/reset-password", json={"token": code, "password": new_password}).status_code == 200

    assert _login(client, email, new_password).status_code == 200


def test_forgot_password_is_limited_per_email(client):
    email = _register(client)

    codes = [client.post("/identity/forgot-password", json={"email": email}).status_code for _ in range(4)]

    assert codes == [200, 200, 200, 429]
    other = client.post("/identity/forgot-password", json={"email": _register(client)})
    assert other.status_code == 200


def test_resend_verification_is_limited_per_email(client):
    email = _register(client)

    codes = [client.post("/identity/resend-verification", json={"email": email}).status_code for _ in range(4)]

    assert codes == [200, 200, 200, 429]


def test_wrong_current_passwords_lock_change_password(client):
    email = _register(client)
    token = _login(client, email, PASSWORD).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def change(current):
        return client.post(
            "/identity/change-password",
            json={"current_password": current, "new_password": "BrandNew-Passphrase-42"},
            headers=headers,
        )

    assert [change(WRONG).status_code for _ in range(5)] == [400] * 5
    _assert_429(change(PASSWORD))
    # The session itself is untouched.
    assert client.get("/identity/whoami", headers=headers).status_code == 200


def test_registration_is_limited_per_ip(client):
    codes = [
        client.post("/identity/users", json={"email": f"rl-{uuid4().hex}@example.com", "password": PASSWORD}).status_code
        for _ in range(31)
    ]

    assert codes[:30] == [201] * 30
    assert codes[30] == 429

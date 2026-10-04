import logging
from uuid import uuid4

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1In0.c2lnbmF0dXJl"
REFRESH = "Zq3J8r0b5mN1-t_QpWxYz7aB2cD4eF6gH8iJ0kL2mN4"
PASSWORD = "Sup3r-Secret-Passphrase!"


def test_auth_requests_put_no_secrets_into_raw_log_records(client, caplog):
    """Checked before any redaction filter: the app must not log them at all.

    At the configured level (INFO). Driver DEBUG output such as aiosqlite's
    statement tracing echoes bound parameters and is not for production.
    """
    caplog.set_level(logging.INFO)
    email = f"logs-{uuid4().hex}@example.com"

    client.post("/identity/users", json={"email": email, "password": PASSWORD})
    login = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]
    client.post("/identity/authenticate", json={"email": email, "password": "Wrong-" + PASSWORD})
    client.post("/identity/refresh", json={"refresh_token": REFRESH})
    client.post("/identity/refresh", json={"refresh_token": login["refresh_token"]})
    client.get("/identity/whoami", headers={"Authorization": f"Bearer {JWT}"})
    client.post("/identity/reset-password", json={"token": REFRESH, "password": PASSWORD})
    client.post("/identity/verify-email", json={"token": REFRESH})

    raw = "\n".join(
        f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records
    )
    for secret in (PASSWORD, REFRESH, JWT, login["refresh_token"], login["access_token"]):
        assert secret not in raw
    assert email not in raw

import json
from uuid import uuid4

from sqlalchemy import select, update

from app.api import identity as identity_api
from app.db.session import SessionLocal
from app.infrastructure.identity.models import (
    LoginEventModel,
    SecurityEventModel,
    UserModel,
    UserStatus,
)

PASSWORD = "StrongPass123!"
WRONG = "WrongPass12345!"
NEW_PASSWORD = "BrandNew-Passphrase-42"


def _db(client, fn):
    async def run():
        async with SessionLocal() as db:
            result = await fn(db)
            await db.commit()
            return result

    return client.portal.call(run)


def _register(client):
    email = f"audit-{uuid4().hex}@example.com"
    user_id = client.post("/identity/users", json={"email": email, "password": PASSWORD}).json()["data"]["id"]
    return email, user_id


def _login(client, email, password, **headers):
    return client.post("/identity/authenticate", json={"email": email, "password": password}, headers=headers)


def _events(client, user_id):
    rows = _db(
        client,
        lambda db: db.scalars(
            select(SecurityEventModel).where(SecurityEventModel.user_id == user_id).order_by(SecurityEventModel.created_at)
        ),
    )
    return [(r.event_type, r.action, json.loads(r.meta_data or "{}"), r.ip_address) for r in rows]


def _actions(client, user_id):
    return [f"{t}.{a}" for t, a, _, _ in _events(client, user_id)]


def _logins(client, **where):
    def query(db):
        stmt = select(LoginEventModel)
        for column, value in where.items():
            stmt = stmt.where(getattr(LoginEventModel, column) == value)
        return db.scalars(stmt)

    return list(_db(client, query))


def _code(email, subject):
    return identity_api.service.email_sender.latest_to(email, subject).body.split("\n\n")[1]


def test_successful_and_failed_sign_ins_are_recorded(client):
    email, user_id = _register(client)

    _login(client, email, PASSWORD, **{"User-Agent": "BUILD-mobile/1.0"})
    _login(client, email, WRONG)

    rows = _logins(client, user_id=user_id)
    assert sorted((r.successful, r.reason) for r in rows) == [(False, "invalid_credentials"), (True, None)]
    success = next(r for r in rows if r.successful)
    assert success.user_agent == "BUILD-mobile/1.0"
    assert success.ip_address == "testclient"


def test_failed_sign_in_for_an_unknown_email_is_recorded_without_the_email(client):
    ghost = f"ghost-{uuid4().hex}@example.com"
    before = len(_logins(client, reason="invalid_credentials"))

    _login(client, ghost, WRONG)

    rows = _logins(client, reason="invalid_credentials")
    assert len(rows) == before + 1
    newest = max(rows, key=lambda r: r.created_at)
    assert newest.user_id is None
    # login_events has no column for the attempted email, and nothing else
    # in the row carries it.
    assert all(ghost not in str(v) for v in vars(newest).values())


def test_blocked_account_sign_in_is_recorded_with_its_reason(client):
    email, user_id = _register(client)
    _db(client, lambda db: db.execute(update(UserModel).where(UserModel.id == user_id).values(status=UserStatus.DISABLED)))

    _login(client, email, PASSWORD)

    assert [(r.successful, r.reason) for r in _logins(client, user_id=user_id)] == [(False, "account_not_active")]


def test_temporary_lock_and_rate_limited_attempts_are_recorded(client):
    email, user_id = _register(client)
    before = len(_logins(client, reason="rate_limited"))

    for _ in range(6):
        _login(client, email, WRONG)

    events = _events(client, user_id)
    lock = [e for e in events if (e[0], e[1]) == ("auth", "temporary_lock")]
    assert len(lock) == 1 and lock[0][2]["scopes"] == ["pair"]
    assert len(_logins(client, reason="rate_limited")) == before + 1


def test_account_lifecycle_events_are_recorded(client):
    email, user_id = _register(client)
    client.post("/identity/verify-email", json={"token": _code(email, "Verify your BUILD email address")})
    client.post("/identity/forgot-password", json={"email": email})
    client.post("/identity/reset-password", json={"token": _code(email, "Reset your BUILD password"), "password": NEW_PASSWORD})

    assert _actions(client, user_id) == [
        "account.registered",
        "email.verified",
        "password.reset_requested",
        "password.reset_completed",
    ]


def test_password_change_success_and_failure_are_recorded(client):
    email, user_id = _register(client)
    session = _login(client, email, PASSWORD).json()["data"]
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    client.post("/identity/change-password", json={"current_password": WRONG, "new_password": NEW_PASSWORD}, headers=headers)
    client.post("/identity/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}, headers=headers)

    events = [(t, a, m) for t, a, m, _ in _events(client, user_id) if t == "password"]
    assert [(t, a) for t, a, _ in events] == [("password", "change_failed"), ("password", "changed")]
    assert events[1][2]["session_id"] == session["session_id"]


def test_refresh_token_reuse_and_logouts_are_recorded(client):
    email, user_id = _register(client)
    first = _login(client, email, PASSWORD).json()["data"]
    client.post("/identity/refresh", json={"refresh_token": first["refresh_token"]})
    client.post("/identity/refresh", json={"refresh_token": first["refresh_token"]})  # reuse

    other = _login(client, email, PASSWORD).json()["data"]
    client.post("/identity/logout", headers={"Authorization": f"Bearer {other['access_token']}"})
    third = _login(client, email, PASSWORD).json()["data"]
    client.post("/identity/logout-all", headers={"Authorization": f"Bearer {third['access_token']}"})

    events = {f"{t}.{a}": m for t, a, m, _ in _events(client, user_id)}
    assert events["session.refresh_token_reuse_detected"]["session_id"] == first["session_id"]
    assert events["session.logout"]["session_id"] == other["session_id"]
    assert events["session.logout_all"]["revoked_sessions"] == 1


def test_events_carry_the_request_id_and_client_ip(client):
    request_id = f"req-{uuid4().hex}"
    email = f"audit-{uuid4().hex}@example.com"
    user_id = client.post(
        "/identity/users", json={"email": email, "password": PASSWORD}, headers={"X-Request-ID": request_id}
    ).json()["data"]["id"]

    ((_, _, meta, ip),) = _events(client, user_id)

    assert meta["request_id"] == request_id
    assert ip == "testclient"


def test_no_secret_ever_reaches_the_event_tables(client):
    email, user_id = _register(client)
    session = _login(client, email, PASSWORD).json()["data"]
    _login(client, email, WRONG)
    client.post("/identity/refresh", json={"refresh_token": session["refresh_token"]})
    client.post("/identity/refresh", json={"refresh_token": session["refresh_token"]})
    client.post("/identity/forgot-password", json={"email": email})
    reset_code = _code(email, "Reset your BUILD password")
    client.post("/identity/reset-password", json={"token": reset_code, "password": NEW_PASSWORD})

    dump = json.dumps(
        [{k: str(v) for k, v in vars(r).items() if not k.startswith("_")} for r in _logins(client, user_id=user_id)]
        + [str(e) for e in _events(client, user_id)]
    )
    for secret in (PASSWORD, WRONG, NEW_PASSWORD, session["access_token"], session["refresh_token"], reset_code):
        assert secret not in dump


def test_a_recording_failure_never_breaks_sign_in(client, monkeypatch):
    def broken_session():
        raise RuntimeError("audit store down")

    monkeypatch.setattr(identity_api.service.security_events, "_session_factory", broken_session)
    email, _ = _register(client)

    assert _login(client, email, PASSWORD).status_code == 200
    assert _login(client, email, WRONG).status_code == 401

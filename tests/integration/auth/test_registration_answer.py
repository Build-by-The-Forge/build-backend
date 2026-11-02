"""Registering can't be used to find accounts (contract: POST /identity/users). The answer
is the same in every way a caller can see, and the work behind it is the same."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.api import identity
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import SessionLocal, engine
from app.infrastructure.identity.models import PendingRegistrationModel, UserModel
from app.main import app
from tests.integration.accounts import register_and_get_id, user_id_for

PASSWORD = "StrongPass123!"
# Differ on every response, whichever the account: not a signal.
PER_RESPONSE = {"x-request-id", "x-response-time-ms", "date"}


def fresh_email() -> str:
    return f"answer-{uuid4().hex}@example.com"


def observable(response) -> tuple[int, bytes, dict[str, str]]:
    headers = {k.lower(): v for k, v in response.headers.items() if k.lower() not in PER_RESPONSE}
    return response.status_code, response.content, headers


def worker_only(monkeypatch) -> None:
    """As deployed: nothing but the worker completes a registration."""
    monkeypatch.setattr(settings, "registration_inline_for_tests", False)


async def _count(model, *where) -> int:
    async with SessionLocal() as session:
        return len((await session.scalars(select(model).where(*where))).all())


def pending_for(client, email: str) -> int:
    return client.portal.call(_count, PendingRegistrationModel, PendingRegistrationModel.email == email)


def users_for(client, email: str) -> int:
    return client.portal.call(_count, UserModel, UserModel.email == email)


def run_worker_pass(client) -> None:
    client.portal.call(identity.service.process_pending_registrations)


# --- the answer ------------------------------------------------------------------------


def test_a_new_and_an_existing_email_get_identical_answers(client):
    existing = fresh_email()
    register_and_get_id(client, {"email": existing, "password": PASSWORD})

    for_new = client.post("/identity/users", json={"email": fresh_email(), "password": PASSWORD})
    for_existing = client.post("/identity/users", json={"email": existing, "password": PASSWORD})

    assert observable(for_new) == observable(for_existing)
    assert for_new.status_code == 202
    assert for_new.content == b""


@pytest.mark.parametrize(
    "password,message",
    [
        ("", "password must be at least 12 characters"),
        ("short", "password must be at least 12 characters"),
        ("x" * 200, "password must be at most 128 characters"),
    ],
)
def test_a_bad_password_is_refused_the_same_whether_or_not_the_account_exists(client, password, message):
    # This was the second form of the leak: 409 if it existed, 422 if it didn't.
    existing = fresh_email()
    register_and_get_id(client, {"email": existing, "password": PASSWORD})

    for_new = client.post("/identity/users", json={"email": fresh_email(), "password": password})
    for_existing = client.post("/identity/users", json={"email": existing, "password": password})

    assert for_new.status_code == for_existing.status_code == 422
    assert for_new.json()["error"] == for_existing.json()["error"]
    assert for_new.json()["error"]["message"] == message


def test_a_badly_formed_email_is_still_refused(client):
    response = client.post("/identity/users", json={"email": "nope", "password": PASSWORD})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "invalid email format"


def test_both_paths_hash_the_password_exactly_once(client, monkeypatch):
    worker_only(monkeypatch)
    existing = fresh_email()
    client.post("/identity/users", json={"email": existing, "password": PASSWORD})
    run_worker_pass(client)

    calls: list[str] = []
    hasher = identity.service.password_hasher
    real = hasher.hash

    def counting(password):
        calls.append(password.value)
        return real(password)

    monkeypatch.setattr(hasher, "hash", counting)
    client.post("/identity/users", json={"email": fresh_email(), "password": PASSWORD})
    after_new = len(calls)
    client.post("/identity/users", json={"email": existing, "password": PASSWORD})

    assert after_new == 1
    assert len(calls) == 2
    run_worker_pass(client)


def _statements_during(client, email: str) -> list[str]:
    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        response = client.post("/identity/users", json={"email": email, "password": PASSWORD})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert response.status_code == 202
    return statements


def test_a_new_and_an_existing_email_run_the_same_statements_and_never_read_users(client, monkeypatch):
    # The account-dependent part is out of the request path altogether, not merely quick.
    worker_only(monkeypatch)
    existing = fresh_email()
    client.post("/identity/users", json={"email": existing, "password": PASSWORD})
    run_worker_pass(client)
    assert users_for(client, existing) == 1

    for_new = _statements_during(client, fresh_email())
    for_existing = _statements_during(client, existing)

    assert for_new == for_existing
    assert for_new, "the listener must see the request's statements"
    assert any("pending_registrations" in statement for statement in for_new)
    assert not any(" users" in statement.lower() for statement in for_new)
    run_worker_pass(client)


async def _call_asgi_recording(client, email: str) -> list[tuple[str, int, int]]:
    """Drives the real application at the ASGI boundary. At each message it sends, reads
    what the database holds for this email, so the order of the two is observed."""
    body = json.dumps({"email": email, "password": PASSWORD}).encode()
    seen: list[tuple[str, int, int]] = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        seen.append(
            (
                message["type"],
                await _count(PendingRegistrationModel, PendingRegistrationModel.email == email),
                await _count(UserModel, UserModel.email == email),
            )
        )

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/identity/users",
        "raw_path": b"/identity/users",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        "client": ("testclient", 1),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return seen


def test_at_the_response_boundary_the_request_is_recorded_and_no_account_exists(client, monkeypatch):
    # The real send boundary, with nothing replaced except that no worker is running.
    worker_only(monkeypatch)
    email = fresh_email()

    seen = client.portal.call(_call_asgi_recording, client, email)

    assert [kind for kind, _, _ in seen] == ["http.response.start", "http.response.body"]
    assert all((pending, users) == (1, 0) for _, pending, users in seen)

    run_worker_pass(client)
    assert (pending_for(client, email), users_for(client, email)) == (0, 1)


# --- durable acceptance -----------------------------------------------------------------


def test_an_accepted_registration_survives_until_a_worker_runs(client, monkeypatch):
    # The crash the in-process version lost: the answer was given, and nothing else ran.
    worker_only(monkeypatch)
    email = fresh_email()

    assert client.post("/identity/users", json={"email": email, "password": PASSWORD}).status_code == 202
    assert (pending_for(client, email), users_for(client, email)) == (1, 0)
    # A later process, with no memory of the request, finishes it.
    run_worker_pass(client)

    assert (pending_for(client, email), users_for(client, email)) == (0, 1)
    assert client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).status_code == 200


def test_if_it_cannot_be_recorded_the_caller_is_told(client, monkeypatch):
    # A 202 now means it's durable, so a failure to record it can't answer 202.
    def failing():
        raise RuntimeError("postgresql://internal/secret-detail")

    monkeypatch.setattr(identity.service, "uow_factory", failing)
    response = client.post("/identity/users", json={"email": fresh_email(), "password": PASSWORD})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-detail" not in response.text


def test_the_stored_row_never_holds_the_password(client, monkeypatch):
    worker_only(monkeypatch)
    email = fresh_email()
    client.post("/identity/users", json={"email": email, "password": PASSWORD})

    async def read():
        async with SessionLocal() as session:
            return await session.scalar(select(PendingRegistrationModel).where(PendingRegistrationModel.email == email))

    row = client.portal.call(read)
    assert PASSWORD not in row.password_hash
    assert row.password_hash.startswith("$argon2")
    run_worker_pass(client)


def test_a_row_that_keeps_failing_is_dropped_rather_than_kept_forever(client, monkeypatch):
    worker_only(monkeypatch)
    email = fresh_email()
    client.post("/identity/users", json={"email": email, "password": PASSWORD})

    async def failing(*_args, **_kwargs):
        raise RuntimeError("database trouble")

    with monkeypatch.context() as broken:
        broken.setattr("app.application.identity.user_service.issue_email_verification", failing)
        for remaining in (1, 1, 1, 1, 0):
            run_worker_pass(client)
            assert pending_for(client, email) == remaining

    assert users_for(client, email) == 0


def test_a_failure_rolls_back_and_the_next_pass_succeeds(client, monkeypatch):
    worker_only(monkeypatch)
    email = fresh_email()
    client.post("/identity/users", json={"email": email, "password": PASSWORD})

    async def failing(*_args, **_kwargs):
        raise RuntimeError("database trouble")

    with monkeypatch.context() as broken:
        broken.setattr("app.application.identity.user_service.issue_email_verification", failing)
        run_worker_pass(client)
    assert (pending_for(client, email), users_for(client, email)) == (1, 0)

    run_worker_pass(client)
    assert (pending_for(client, email), users_for(client, email)) == (0, 1)


def test_one_bad_row_does_not_hold_up_the_others(client, monkeypatch):
    worker_only(monkeypatch)
    bad, good = fresh_email(), fresh_email()
    client.post("/identity/users", json={"email": bad, "password": PASSWORD})
    client.post("/identity/users", json={"email": good, "password": PASSWORD})

    async def failing_for_bad(repository, user, lifetime):
        if user.email.value == bad:
            raise RuntimeError("database trouble")
        return await real_issue(repository, user, lifetime)

    import app.application.identity.user_service as module

    real_issue = module.issue_email_verification
    with monkeypatch.context() as broken:
        broken.setattr(module, "issue_email_verification", failing_for_bad)
        run_worker_pass(client)

    assert (pending_for(client, bad), users_for(client, bad)) == (1, 0)
    assert (pending_for(client, good), users_for(client, good)) == (0, 1)
    run_worker_pass(client)


# --- what the worker does ---------------------------------------------------------------


def test_registering_again_changes_nothing_about_the_account(client):
    email = fresh_email()
    first_id = register_and_get_id(client, {"email": email, "password": PASSWORD})

    other_password = "Another-Passphrase-1"
    assert client.post("/identity/users", json={"email": email, "password": other_password}).status_code == 202

    assert client.portal.call(user_id_for, email) == first_id
    assert pending_for(client, email) == 0
    assert client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).status_code == 200
    assert client.post("/identity/authenticate", json={"email": email, "password": other_password}).status_code == 401


def test_a_verification_email_goes_only_to_a_new_account(client, monkeypatch):
    sent: list[str] = []

    async def recording(message):
        sent.append(message.to)

    monkeypatch.setattr(identity.service.email_sender, "send", recording)
    email = fresh_email()
    client.post("/identity/users", json={"email": email, "password": PASSWORD})
    assert sent == [email]

    client.post("/identity/users", json={"email": email, "password": PASSWORD})
    assert sent == [email]


def test_an_undelivered_email_changes_nothing_a_caller_can_see(client, monkeypatch):
    async def failing(message):
        raise RuntimeError("smtp://internal-mail/secret-detail")

    monkeypatch.setattr(identity.service.email_sender, "send", failing)
    email = fresh_email()

    response = client.post("/identity/users", json={"email": email, "password": PASSWORD})

    assert response.status_code == 202
    assert response.content == b""
    assert client.portal.call(user_id_for, email)
    assert pending_for(client, email) == 0


def test_a_duplicate_registers_no_security_event(client, monkeypatch):
    email = fresh_email()
    register_and_get_id(client, {"email": email, "password": PASSWORD})
    recorded: list[object] = []

    async def recording(event_type, **_):
        recorded.append(event_type)

    monkeypatch.setattr(identity.service.security_events, "record", recording)
    client.post("/identity/users", json={"email": email, "password": PASSWORD})
    assert recorded == []


def test_a_throttled_or_failing_registration_keeps_the_error_shape(client, monkeypatch):
    async def down(_ip):
        raise AppError("internal detail", status_code=503)

    monkeypatch.setattr(identity.throttle, "register", down)
    response = client.post("/identity/users", json={"email": fresh_email(), "password": PASSWORD})
    assert response.status_code == 503
    assert "internal detail" not in response.text


def test_the_old_answers_are_gone_from_the_route(client):
    # Neither a 201 with the user nor a 409, whatever the email.
    email = fresh_email()
    first = client.post("/identity/users", json={"email": email, "password": PASSWORD})
    second = client.post("/identity/users", json={"email": email.upper(), "password": PASSWORD})
    assert first.status_code == second.status_code == 202
    assert email not in first.text


# --- the test-only inline path ----------------------------------------------------------


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_inline_completion_is_refused_where_timing_could_matter(environment):
    from app.core.config import Settings

    boundary = {
        "ai_service_url": "https://ai-service.internal",
        "backend_to_ai_secret": "b" * 40,
        "ai_to_backend_secret": "a" * 40,
        "auth_jwt_secret": "j" * 40,
    }
    with pytest.raises(ValueError, match="REGISTRATION_INLINE_FOR_TESTS"):
        Settings(_env_file=None, app_environment=environment, registration_inline_for_tests=True, **boundary)

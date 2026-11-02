"""Registering can't be used to find accounts (contract: POST /identity/users). The answer
is the same in every way a caller can see, and the work before it is the same."""

import asyncio
from uuid import uuid4

import pytest

from app.api import identity
from app.core.config import Settings, settings
from app.core.exceptions import AppError
from tests.integration.accounts import register_and_get_id, user_id_for

PASSWORD = "StrongPass123!"
# Differ on every response, whichever the account: not a signal.
PER_RESPONSE = {"x-request-id", "x-response-time-ms", "date"}


def fresh_email() -> str:
    return f"answer-{uuid4().hex}@example.com"


def observable(response) -> tuple[int, bytes, dict[str, str]]:
    headers = {k.lower(): v for k, v in response.headers.items() if k.lower() not in PER_RESPONSE}
    return response.status_code, response.content, headers


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
    existing = fresh_email()
    register_and_get_id(client, {"email": existing, "password": PASSWORD})

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


def test_registering_again_changes_nothing_about_the_account(client):
    email = fresh_email()
    first_id = register_and_get_id(client, {"email": email, "password": PASSWORD})

    other_password = "Another-Passphrase-1"
    assert client.post("/identity/users", json={"email": email, "password": other_password}).status_code == 202

    assert client.portal.call(user_id_for, email) == first_id
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


def test_a_duplicate_registers_no_security_event(client, monkeypatch):
    email = fresh_email()
    register_and_get_id(client, {"email": email, "password": PASSWORD})
    recorded: list[object] = []

    async def recording(event, **_):
        recorded.append(event)

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


def test_the_answer_is_given_without_touching_the_database(client, monkeypatch):
    # Whatever the database would say can't reach the answer if nothing asks it. This is
    # the guarantee the timing measurement can only estimate.
    existing = fresh_email()
    register_and_get_id(client, {"email": existing, "password": PASSWORD})

    def no_database():
        raise AssertionError("registration looked at the database before answering")

    async def not_yet(_request):
        return None

    monkeypatch.setattr(identity.service, "uow_factory", no_database)
    monkeypatch.setattr(identity.service, "repository", None)
    monkeypatch.setattr(identity.service, "complete_registration", not_yet)

    for_new = client.post("/identity/users", json={"email": fresh_email(), "password": PASSWORD})
    for_existing = client.post("/identity/users", json={"email": existing, "password": PASSWORD})

    assert observable(for_new) == observable(for_existing)
    assert for_new.status_code == 202


def test_a_database_failure_after_answering_reaches_no_one(client, monkeypatch):
    def failing():
        raise RuntimeError("postgresql://internal/secret-detail")

    monkeypatch.setattr(identity.service, "uow_factory", failing)
    response = client.post("/identity/users", json={"email": fresh_email(), "password": PASSWORD})

    assert response.status_code == 202
    assert response.content == b""


@pytest.mark.parametrize("jitter,waits", [(0.0, False), (0.25, True)])
def test_the_work_after_the_answer_starts_at_a_random_point(client, monkeypatch, jitter, waits):
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def recording(seconds):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(settings, "registration_completion_jitter_seconds", jitter)
    monkeypatch.setattr("app.application.identity.user_service.asyncio.sleep", recording)
    email = fresh_email()
    response = client.post("/identity/users", json={"email": email, "password": PASSWORD})

    assert response.status_code == 202
    assert client.portal.call(user_id_for, email)
    if waits:
        assert len(slept) == 1 and 0 <= slept[0] <= jitter
    else:
        assert slept == []


def test_the_default_keeps_the_work_unaligned():
    assert Settings.model_fields["registration_completion_jitter_seconds"].default == 1.0

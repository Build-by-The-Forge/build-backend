"""Typed identity bodies (M3-B, G-14). A malformed body is VALIDATION_FAILED, and every
deliberate business refusal keeps its own answer."""

from uuid import uuid4

import pytest

from tests.integration.accounts import register_and_get_id
from tests.integration.assessment.test_question_api import verify_email
from tests.integration.tenant.test_my_memberships_api import seed_tenant_membership

PASSWORD = "StrongPass123!"
NEW_EMAIL = "someone-new@example.com"

MISSING = [
    ("/identity/users", {"password": PASSWORD}),
    ("/identity/users", {"email": NEW_EMAIL}),
    ("/identity/authenticate", {"password": PASSWORD}),
    ("/identity/authenticate", {"email": NEW_EMAIL}),
    ("/identity/refresh", {}),
    ("/identity/verify-email", {}),
    ("/identity/resend-verification", {}),
    ("/identity/forgot-password", {}),
    ("/identity/reset-password", {"password": PASSWORD}),
    ("/identity/reset-password", {"token": "x"}),
]
WRONG_TYPE = [
    ("/identity/users", {"email": NEW_EMAIL, "password": 7}),
    ("/identity/authenticate", {"email": 7, "password": PASSWORD}),
    ("/identity/refresh", {"refresh_token": 7}),
    ("/identity/verify-email", {"token": ["x"]}),
    ("/identity/forgot-password", {"email": {"a": 1}}),
    ("/identity/reset-password", {"token": "x", "password": 7}),
]
EXTRA = [
    ("/identity/authenticate", {"email": NEW_EMAIL, "password": PASSWORD, "is_admin": True}),
    ("/identity/refresh", {"refresh_token": "x", "user_id": "y"}),
    ("/identity/forgot-password", {"email": NEW_EMAIL, "tenant_id": "y"}),
]


def account(client) -> tuple[str, dict[str, str]]:
    email = f"bodies-{uuid4()}@example.com"
    payload = {"email": email, "password": PASSWORD}
    assert client.post("/identity/users", json=payload).status_code == 202
    token = client.post("/identity/authenticate", json=payload).json()["data"]["access_token"]
    return email, {"Authorization": f"Bearer {token}"}


def assert_refused(response, status_code: int, code: str, message: str | None = None) -> None:
    assert response.status_code == status_code, response.text
    assert response.json()["error"]["code"] == code
    if message is not None:
        assert response.json()["error"]["message"] == message


@pytest.mark.parametrize("path,body", MISSING + WRONG_TYPE + EXTRA)
def test_a_malformed_body_is_a_validation_failure(client, path, body):
    assert_refused(client.post(path, json=body), 422, "VALIDATION_FAILED", "validation failed")


@pytest.mark.parametrize("path,body", MISSING)
def test_a_missing_field_is_named(client, path, body):
    fields = client.post(path, json=body).json()["error"]["details"]["fields"]
    assert all(field["code"] == "missing" and field["field"].startswith("body.") for field in fields)
    assert "*" not in fields[0]["field"]


def test_a_body_that_is_not_an_object_is_a_validation_failure(client):
    assert_refused(client.post("/identity/authenticate", json=["x"]), 422, "VALIDATION_FAILED")


# --- deliberate business refusals keep their answers ---------------------------------------


@pytest.mark.parametrize("password", ["", "x" * 5000])
def test_a_blank_or_oversized_password_at_sign_in_is_still_wrong_credentials(client, password):
    email, _ = account(client)
    response = client.post("/identity/authenticate", json={"email": email, "password": password})
    assert_refused(response, 401, "AUTH_INVALID_CREDENTIALS", "invalid credentials")


def test_a_blank_refresh_token_is_still_invalid_so_the_client_signs_out(client):
    assert_refused(client.post("/identity/refresh", json={"refresh_token": ""}), 401, "AUTH_REFRESH_INVALID")


@pytest.mark.parametrize("path", ["/identity/resend-verification", "/identity/forgot-password"])
def test_a_badly_formed_email_keeps_its_own_message(client, path):
    assert_refused(client.post(path, json={"email": "nope"}), 422, "VALIDATION_FAILED", "invalid email format")


def test_a_short_password_keeps_its_own_message(client):
    response = client.post("/identity/users", json={"email": f"s-{uuid4()}@example.com", "password": "short"})
    assert_refused(response, 422, "VALIDATION_FAILED", "password must be at least 12 characters")


@pytest.mark.parametrize(
    "path,body,message",
    [
        ("/identity/verify-email", {"token": "not-a-real-code"}, "invalid verification token"),
        ("/identity/reset-password", {"token": "not-a-real-code", "password": PASSWORD}, "invalid reset token"),
    ],
)
def test_a_bad_emailed_token_is_400_as_the_contract_says(client, path, body, message):
    # Not 401, which tells a client to refresh its session and try again.
    assert_refused(client.post(path, json=body), 400, "TOKEN_INVALID", message)


@pytest.mark.parametrize(
    "path,body", [("/identity/verify-email", {"token": ""}), ("/identity/reset-password", {"token": "", "password": PASSWORD})]
)
def test_a_blank_emailed_token_is_a_validation_failure(client, path, body):
    assert_refused(client.post(path, json=body), 422, "VALIDATION_FAILED")


# --- change-password ------------------------------------------------------------------------


def test_a_wrong_current_password_has_its_own_code_and_is_never_401(client):
    _, bearer = account(client)
    body = {"current_password": "WrongPass12345!", "new_password": PASSWORD + "1"}
    response = client.post("/identity/change-password", json=body, headers=bearer)
    assert_refused(response, 400, "CURRENT_PASSWORD_INCORRECT", "current password is incorrect")


@pytest.mark.parametrize(
    "body",
    [
        {"new_password": PASSWORD + "1"},
        {"current_password": PASSWORD},
        {"current_password": 7, "new_password": PASSWORD + "1"},
        {"current_password": PASSWORD, "new_password": PASSWORD + "1", "revoke_other_sessions": "yes"},
        {"current_password": PASSWORD, "new_password": PASSWORD + "1", "revoke_other_sessions": 1},
    ],
)
def test_a_malformed_change_password_body_changes_nothing(client, body):
    email, bearer = account(client)
    assert_refused(client.post("/identity/change-password", json=body, headers=bearer), 422, "VALIDATION_FAILED")
    assert client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).status_code == 200


def test_a_malformed_change_password_body_still_needs_a_token(client):
    assert client.post("/identity/change-password", json={}).status_code == 401


# --- device handling ------------------------------------------------------------------------


def sign_in(client, email: str, **extra):
    return client.post("/identity/authenticate", json={"email": email, "password": PASSWORD, **extra})


def test_a_new_device_is_recorded_at_sign_in_and_returned(client):
    email, _ = account(client)
    device = str(uuid4())
    response = sign_in(client, email, device_id=device, user_agent="BUILD/1.0")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["device_id"] == device


def test_the_same_device_signs_in_again(client):
    email, _ = account(client)
    device = str(uuid4())
    assert sign_in(client, email, device_id=device).status_code == 200
    assert sign_in(client, email, device_id=device).json()["data"]["device_id"] == device


def test_another_users_device_is_not_linked_and_the_sign_in_still_works(client):
    first, _ = account(client)
    second, _ = account(client)
    device = str(uuid4())
    assert sign_in(client, first, device_id=device).json()["data"]["device_id"] == device
    response = sign_in(client, second, device_id=device)
    assert response.status_code == 200
    assert response.json()["data"]["device_id"] is None


def test_a_failed_sign_in_records_no_device(client):
    email, _ = account(client)
    device = str(uuid4())
    wrong = client.post("/identity/authenticate", json={"email": email, "password": "WrongPass12345!", "device_id": device})
    assert wrong.status_code == 401
    # Had it been recorded for this user, the next user couldn't have it.
    other, _ = account(client)
    assert sign_in(client, other, device_id=device).json()["data"]["device_id"] == device


def test_no_device_is_fine(client):
    email, _ = account(client)
    assert sign_in(client, email).json()["data"]["device_id"] is None


@pytest.mark.parametrize("device", ["x" * 37, "", "has space", "<script>", "a/b"])
def test_a_device_id_that_cannot_be_stored_is_a_validation_failure(client, device):
    email, _ = account(client)
    assert_refused(sign_in(client, email, device_id=device), 422, "VALIDATION_FAILED")


def test_an_oversized_user_agent_is_a_validation_failure(client):
    email, _ = account(client)
    assert_refused(sign_in(client, email, user_agent="x" * 513), 422, "VALIDATION_FAILED")


# --- a validation failure never carries the secret ------------------------------------------


@pytest.mark.parametrize(
    "path,body",
    [
        ("/identity/authenticate", {"email": "a@example.com", "password": ["the-secret-value"]}),
        ("/identity/reset-password", {"token": ["the-secret-value"], "password": "the-secret-value"}),
        ("/identity/refresh", {"refresh_token": {"the-secret-value": 1}}),
    ],
)
def test_a_refused_secret_is_not_echoed(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 422
    assert "the-secret-value" not in response.text


def test_memberships_no_longer_carry_the_tenant_id(client):
    email = f"bodies-{uuid4()}@example.com"
    payload = {"email": email, "password": PASSWORD}
    user_id = register_and_get_id(client, payload)
    token = client.post("/identity/authenticate", json=payload).json()["data"]["access_token"]
    client.portal.call(seed_tenant_membership, f"bodies-{uuid4().hex[:10]}", user_id, "student")

    response = client.get("/identity/memberships", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    entries = response.json()["data"]
    assert len(entries) == 1
    assert set(entries[0]) == {"tenant_slug", "tenant_name", "membership_id", "role"}


def test_accepting_an_invitation_needs_a_token_field(client):
    # A verified account, so nothing but the body can be the reason.
    email, _ = account(client)
    verify_email(client, email)
    token = client.post("/identity/authenticate", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    response = client.post("/invitations/accept", json={}, headers={"Authorization": f"Bearer {token}"})
    assert_refused(response, 422, "VALIDATION_FAILED", "validation failed")
    assert [field["field"] for field in response.json()["error"]["details"]["fields"]] == ["body.token"]

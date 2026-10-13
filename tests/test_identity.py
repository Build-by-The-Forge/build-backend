import pytest
from fastapi.testclient import TestClient
from starlette import status

from app.api import identity as identity_api
from app.domain.identity.user import Device, Session, User
from app.domain.identity.value_objects import (
    DeviceId,
    Email,
    Password,
    PasswordHash,
    RefreshTokenHash,
    SessionId,
    UserId,
)
from app.events.event_bus import EventBus
from app.infrastructure.security.argon2_password_hasher import Argon2PasswordHasher
from app.main import app


@pytest.fixture(scope="module")
def client():
    """
    Module scoped client so data persists across tests
    (your duplicate email test relies on it).
    Using `with` triggers lifespan -> initialize_database() -> create_all()
    """
    with TestClient(app) as c:
        yield c


def test_register_user_creates_identity_record(client) -> None:
    response = client.post(
        "/identity/users",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["email"] == "student@example.com"
    assert payload["data"]["is_active"] is True


def test_duplicate_user_email_is_rejected(client) -> None:
    first = client.post(
        "/identity/users",
        json={"email": "dup@example.com", "password": "StrongPass123!"},
    )
    second = client.post(
        "/identity/users",
        json={"email": "dup@example.com", "password": "StrongPass123!"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["success"] is False


def test_invalid_email_is_rejected(client) -> None:
    response = client.post(
        "/identity/users",
        json={"email": "not-an-email", "password": "StrongPass123!"},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_weak_password_is_rejected(client) -> None:
    response = client.post(
        "/identity/users",
        json={"email": "weak@example.com", "password": "short"},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_malformed_payload_returns_validation_error_shape(client) -> None:
    response = client.post(
        "/identity/users",
        json={"email": 42, "password": "StrongPass123!"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] == {}
    assert "error" in payload["meta"] or "details" in payload["meta"]


def test_user_aggregate_can_change_password_to_hash() -> None:
    user = User(
        id=UserId(""),
        email=Email("owner@example.com"),
        password_hash=PasswordHash("initial"),
    )

    new_password = Password("NewStrongPass123!")
    user.change_password(new_password, Argon2PasswordHasher())

    assert user.password_hash.value != new_password.value
    assert user.password_hash.value.startswith("$argon2id$")


def test_event_bus_notifies_subscribers() -> None:
    bus = EventBus()
    events: list[str] = []

    def subscriber(event: object) -> None:
        events.append(event.event_type)

    bus.subscribe("user.registered", subscriber)
    bus.publish("user.registered", payload={"user_id": "123"})

    assert events == ["user.registered"]


def test_authenticate_user_returns_session_for_valid_credentials(client) -> None:
    client.post(
        "/identity/users",
        json={"email": "auth@example.com", "password": "StrongPass123!"},
    )

    response = client.post(
        "/identity/authenticate",
        json={"email": "auth@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "user_id" in payload["data"]


def test_refresh_and_logout_flow_round_trips_through_identity_api(client) -> None:
    email = "refresh-flow@example.com"
    client.post(
        "/identity/users",
        json={"email": email, "password": "StrongPass123!"},
    )

    auth_response = client.post(
        "/identity/authenticate",
        json={"email": email, "password": "StrongPass123!"},
    )

    assert auth_response.status_code == 200
    auth_payload = auth_response.json()
    assert auth_payload["success"] is True
    assert auth_payload["data"]["refresh_token"]

    refresh_response = client.post(
        "/identity/refresh",
        json={"refresh_token": auth_payload["data"]["refresh_token"]},
    )

    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.json()
    assert refresh_payload["success"] is True
    assert refresh_payload["data"]["session_id"] == auth_payload["data"]["session_id"]
    assert refresh_payload["data"]["refresh_token"] != auth_payload["data"]["refresh_token"]

    logout_response = client.post(
        "/identity/logout",
        headers={"Authorization": f"Bearer {refresh_payload['data']['access_token']}"},
    )

    assert logout_response.status_code == 200


def test_current_user_endpoint_returns_authenticated_user(client) -> None:
    email = "me@example.com"
    client.post(
        "/identity/users",
        json={"email": email, "password": "StrongPass123!"},
    )

    auth_response = client.post(
        "/identity/authenticate",
        json={"email": email, "password": "StrongPass123!"},
    )

    assert auth_response.status_code == 200
    access_token = auth_response.json()["data"]["access_token"]

    me_response = client.get(
        "/identity/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert me_response.status_code == 200
    payload = me_response.json()
    assert payload["success"] is True
    assert payload["data"]["email"] == email


def test_password_reset_flow_allows_sign_in_with_new_password(client) -> None:
    email = "recover@example.com"
    client.post(
        "/identity/users",
        json={"email": email, "password": "StrongPass123!"},
    )

    forgot_response = client.post(
        "/identity/forgot-password",
        json={"email": email},
    )

    assert forgot_response.status_code == 200
    assert forgot_response.json()["data"] == {}
    reset_token = identity_api.service.email_sender.latest_to(email, "Reset your BUILD password").body.split("\n\n")[1]

    reset_response = client.post(
        "/identity/reset-password",
        json={"token": reset_token, "password": "NewStrongPass123!"},
    )

    assert reset_response.status_code == 200

    auth_response = client.post(
        "/identity/authenticate",
        json={"email": email, "password": "NewStrongPass123!"},
    )

    assert auth_response.status_code == 200
    assert auth_response.json()["success"] is True


def test_session_can_be_revoked_and_touched() -> None:
    session = Session(
        id=SessionId("session-1"),
        user_id=UserId("user-1"),
        device_id=DeviceId("device-1"),
        refresh_token_hash=RefreshTokenHash("refresh-token"),
    )

    session.touch()
    session.revoke()

    assert session.last_seen_at is not None
    assert session.revoked_at is not None


def test_device_can_be_marked_trusted_and_touched() -> None:
    device = Device(id=DeviceId("device-1"), platform="ios")

    device.touch()
    device.mark_trusted()

    assert device.last_seen is not None
    assert device.trusted is True

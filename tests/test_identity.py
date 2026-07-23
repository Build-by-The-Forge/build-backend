from app.domain.identity.user import Device, RefreshToken, Session, User
from app.domain.identity.value_objects import (
    DeviceId,
    Email,
    Password,
    PasswordHash,
    PasswordHasher,
    Permission,
    PermissionId,
    RefreshTokenHash,
    RefreshTokenId,
    Role,
    RoleId,
    SessionId,
    UserId,
)
from app.events.event_bus import EventBus
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_register_user_creates_identity_record() -> None:
    response = client.post(
        "/identity/users",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["email"] == "student@example.com"
    assert payload["data"]["is_active"] is True


def test_duplicate_user_email_is_rejected() -> None:
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


def test_invalid_email_is_rejected() -> None:
    response = client.post(
        "/identity/users",
        json={"email": "not-an-email", "password": "StrongPass123!"},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_weak_password_is_rejected() -> None:
    response = client.post(
        "/identity/users",
        json={"email": "weak@example.com", "password": "short"},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_user_aggregate_can_change_password_to_hash() -> None:
    user = User(
        id=UserId(""),
        email=Email("owner@example.com"),
        password_hash=PasswordHash("initial"),
    )

    new_password = Password("NewStrongPass123!")
    user.change_password(new_password, PasswordHasher())

    assert user.password_hash.value != new_password.value
    assert user.password_hash.value.startswith("hashed:")


def test_user_can_assign_role() -> None:
    user = User(
        id=UserId(""),
        email=Email("owner@example.com"),
        password_hash=PasswordHash("initial"),
    )
    role = Role(id=RoleId("role-1"), name="student")

    user.assign_role(role)

    assert role in user.roles


def test_event_bus_notifies_subscribers() -> None:
    bus = EventBus()
    events: list[str] = []

    def subscriber(event: object) -> None:
        events.append(event.event_type)

    bus.subscribe("user.registered", subscriber)
    bus.publish("user.registered", payload={"user_id": "123"})

    assert events == ["user.registered"]


def test_authenticate_user_returns_session_for_valid_credentials() -> None:
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
    assert payload["data"]["user_id"] == payload["data"]["user_id"]


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


def test_refresh_token_can_be_rotated_and_revoked() -> None:
    token = RefreshToken(
        id=RefreshTokenId("refresh-1"),
        session_id=SessionId("session-1"),
        token_hash=RefreshTokenHash("old-hash"),
    )

    token.rotate(RefreshTokenHash("new-hash"))
    token.revoke()

    assert token.token_hash.value == "new-hash"
    assert token.rotated_at is not None
    assert token.revoked_at is not None

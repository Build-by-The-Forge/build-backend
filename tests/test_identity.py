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

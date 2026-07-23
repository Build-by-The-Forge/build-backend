from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_live() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "BUILD backend is running" in payload["data"]["message"]

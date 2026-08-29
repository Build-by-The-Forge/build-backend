from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_ready_returns_status() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ready", "degraded"}


def test_metrics_endpoint_is_available() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "build_backend_requests_total" in response.text


def test_request_id_header_is_added() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert "x-request-id" in response.headers

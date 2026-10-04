from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_unknown_route_is_404_not_500():
    resp = client.get("/definitely-not-a-route")

    assert resp.status_code == 404
    assert resp.json()["success"] is False


def test_wrong_method_is_405_with_allow_header():
    resp = client.post("/health/live")

    assert resp.status_code == 405
    assert "GET" in resp.headers.get("allow", "")


def test_missing_bearer_keeps_www_authenticate():
    resp = client.get("/identity/whoami")

    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"

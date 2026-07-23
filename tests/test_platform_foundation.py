from app.bootstrap.container import build_container
from app.events.event_bus import EventBus
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_event_bus_delivers_events() -> None:
    received: list[str] = []
    bus = EventBus()
    bus.subscribe("user.registered", lambda event: received.append(event.event_type))
    bus.publish("user.registered", event_type="user.registered")
    assert received == ["user.registered"]


def test_container_builds_platform_services() -> None:
    container = build_container()
    assert isinstance(container.get(EventBus), EventBus)


def test_root_response_is_enveloped() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["message"].startswith("BUILD backend")
    assert payload["request_id"]

"""The learning-memory production gate: when startup refuses."""

import pytest
from pydantic import ValidationError

from app.core import learning_memory_gate as gate
from app.core.config import Settings

SECRETS = {
    "AUTH_JWT_SECRET": "j" * 48,
    "AI_SERVICE_URL": "https://ai-service.internal",
    "BACKEND_TO_AI_SECRET": "b2a-" + "x" * 40,
    "AI_TO_BACKEND_SECRET": "a2b-" + "z" * 40,
}
ALL_ENVIRONMENTS = ["development", "testing", "staging", "production"]


def make(environment: str, **values) -> Settings:
    return Settings(_env_file=None, app_environment=environment, **SECRETS, **values)


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv("LEARNING_MEMORY_ENABLED", raising=False)
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def marker(monkeypatch, tmp_path):
    path = tmp_path / "production-image"
    path.touch()
    monkeypatch.setattr(gate, "PRODUCTION_IMAGE_MARKER", path)


@pytest.fixture
def no_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "PRODUCTION_IMAGE_MARKER", tmp_path / "absent")


@pytest.mark.parametrize("environment", ALL_ENVIRONMENTS)
def test_memory_is_off_by_default(environment, no_marker):
    assert make(environment).learning_memory_allowed is False


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_development_and_testing_may_turn_it_on_outside_the_production_image(environment, no_marker):
    assert make(environment, learning_memory_enabled=True).learning_memory_allowed is True


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_strict_environments_refuse_to_start_with_it_on(environment, no_marker):
    with pytest.raises(ValidationError, match="LEARNING_MEMORY_ENABLED is refused"):
        make(environment, learning_memory_enabled=True)


@pytest.mark.parametrize("environment", ALL_ENVIRONMENTS)
def test_the_production_image_refuses_whatever_the_environment_says(environment, marker):
    with pytest.raises(ValidationError, match="LEARNING_MEMORY_ENABLED is refused"):
        make(environment, learning_memory_enabled=True)


@pytest.mark.parametrize("environment", ALL_ENVIRONMENTS)
def test_the_production_image_starts_with_it_off(environment, marker):
    assert make(environment).learning_memory_allowed is False


@pytest.mark.parametrize("value", ["maybe", "", "2"])
def test_a_malformed_value_fails_startup(monkeypatch, value, no_marker):
    monkeypatch.setenv("LEARNING_MEMORY_ENABLED", value)
    with pytest.raises(ValidationError):
        make("development")


@pytest.mark.parametrize("environment", ALL_ENVIRONMENTS)
def test_opening_the_constant_lets_the_setting_decide_everywhere(monkeypatch, environment, marker):
    monkeypatch.setattr(gate, "GATE_OPEN", True)
    assert make(environment, learning_memory_enabled=True).learning_memory_allowed is True
    assert make(environment).learning_memory_allowed is False


def test_the_gate_ships_closed():
    assert gate.GATE_OPEN is False


def test_a_marker_that_cannot_be_examined_fails_closed(monkeypatch):
    class Unreadable:
        def exists(self):
            raise PermissionError("denied")

    monkeypatch.setattr(gate, "PRODUCTION_IMAGE_MARKER", Unreadable())
    with pytest.raises(PermissionError):
        gate.memory_allowed(True, "development")

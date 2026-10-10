"""Service-boundary configuration (design A.1, B.7; acceptance row C26)."""

import pytest
from app.core.config import KNOWN_DEVELOPMENT_SERVICE_SECRETS, Settings

JWT = "j" * 40
URL = "http://ai-service:8000"
B2A = "b2a-" + "x" * 40
B2A_OLD = "b2a-old-" + "y" * 40
A2B = "a2b-" + "z" * 40
A2B_OLD = "a2b-old-" + "w" * 40


@pytest.fixture(autouse=True)
def no_ambient_service_env(monkeypatch):
    for name in (
        "AI_SERVICE_URL",
        "BACKEND_TO_AI_SECRET",
        "BACKEND_TO_AI_SECRET_PREVIOUS",
        "AI_TO_BACKEND_SECRET",
        "AI_TO_BACKEND_SECRET_PREVIOUS",
        "AUTH_JWT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def make(environment: str, **overrides) -> Settings:
    values = {
        "app_environment": environment,
        "auth_jwt_secret": JWT,
        "ai_service_url": URL,
        "backend_to_ai_secret": B2A,
        "ai_to_backend_secret": A2B,
    }
    values.update(overrides)
    return Settings(_env_file=None, **{k: v for k, v in values.items() if v is not None})


STRICT = ["staging", "production"]


@pytest.mark.parametrize("environment", STRICT)
def test_complete_configuration_starts(environment):
    settings = make(
        environment,
        backend_to_ai_secret_previous=B2A_OLD,
        ai_to_backend_secret_previous=A2B_OLD,
    )
    assert settings.ai_to_backend_verification_secrets == (A2B, A2B_OLD)
    assert settings.backend_to_ai_secret == B2A
    assert settings.ai_service_url == URL


@pytest.mark.parametrize("environment", STRICT)
@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("backend_to_ai_secret", "BACKEND_TO_AI_SECRET is required"),
        ("ai_to_backend_secret", "AI_TO_BACKEND_SECRET is required"),
        ("ai_service_url", "AI_SERVICE_URL is required"),
    ],
)
def test_missing_required_setting_refuses_to_start(environment, field, message):
    values = {
        "app_environment": environment,
        "auth_jwt_secret": JWT,
        "ai_service_url": URL,
        "backend_to_ai_secret": B2A,
        "ai_to_backend_secret": A2B,
    }
    del values[field]
    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize("environment", STRICT)
@pytest.mark.parametrize(
    "field",
    [
        "backend_to_ai_secret",
        "ai_to_backend_secret",
        "backend_to_ai_secret_previous",
        "ai_to_backend_secret_previous",
    ],
)
def test_short_secret_refuses_to_start(environment, field):
    with pytest.raises(ValueError, match="at least 32 bytes"):
        make(environment, **{field: "s" * 31})


def test_secret_length_is_counted_in_bytes():
    make("production", backend_to_ai_secret="é" * 16)  # 32 bytes


@pytest.mark.parametrize("environment", STRICT)
@pytest.mark.parametrize(
    "known", sorted(v for v in KNOWN_DEVELOPMENT_SERVICE_SECRETS if len(v) >= 32)
)
def test_known_development_value_refuses_to_start(environment, known):
    with pytest.raises(ValueError, match="known development value"):
        make(environment, backend_to_ai_secret=known)
    with pytest.raises(ValueError, match="known development value"):
        make(environment, ai_to_backend_secret=known)


def test_former_short_defaults_are_refused_by_length():
    for known in (v for v in KNOWN_DEVELOPMENT_SERVICE_SECRETS if len(v) < 32):
        with pytest.raises(ValueError, match="at least 32 bytes"):
            make("production", ai_to_backend_secret=known)


@pytest.mark.parametrize("environment", ["development", "testing", "staging", "production"])
def test_equal_directional_secrets_refuse_to_start(environment):
    with pytest.raises(ValueError, match="must differ"):
        make(environment, backend_to_ai_secret=A2B, ai_to_backend_secret=A2B)


@pytest.mark.parametrize(
    "overrides",
    [
        {"backend_to_ai_secret_previous": A2B},
        {"ai_to_backend_secret_previous": B2A},
        {
            "backend_to_ai_secret_previous": "shared-" + "q" * 40,
            "ai_to_backend_secret_previous": "shared-" + "q" * 40,
        },
    ],
)
def test_directions_never_share_a_secret_across_rotation(overrides):
    with pytest.raises(ValueError, match="must differ"):
        make("production", **overrides)


def test_previous_secret_needs_a_current_one():
    with pytest.raises(ValueError, match="AI_TO_BACKEND_SECRET_PREVIOUS requires"):
        Settings(
            _env_file=None,
            app_environment="development",
            ai_to_backend_secret_previous=A2B_OLD,
        )


def test_short_secret_is_refused_in_development_too():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        Settings(_env_file=None, app_environment="development", backend_to_ai_secret="short")


def test_development_has_no_built_in_secrets_and_a_local_ai_url():
    settings = Settings(_env_file=None, app_environment="development")
    assert settings.backend_to_ai_secret is None
    assert settings.ai_to_backend_secret is None
    assert settings.ai_to_backend_verification_secrets == ()
    assert settings.ai_service_url == "http://localhost:8001"


def test_development_accepts_the_test_vector_secrets_for_local_work():
    Settings(
        _env_file=None,
        app_environment="development",
        backend_to_ai_secret="test-only-backend-to-ai-secret-0123456789abcdef",
        ai_to_backend_secret="test-only-ai-to-backend-secret-fedcba9876543210",
    )


def test_testing_generates_distinct_random_secrets_per_process():
    first = Settings(_env_file=None, app_environment="testing")
    second = Settings(_env_file=None, app_environment="testing")
    assert first.backend_to_ai_secret != first.ai_to_backend_secret
    assert first.ai_to_backend_secret != second.ai_to_backend_secret
    assert len((first.ai_to_backend_secret or "").encode()) >= 32


def test_static_bearer_settings_are_gone():
    settings = Settings(_env_file=None, app_environment="development")
    assert not hasattr(settings, "ai_service_api_key")
    assert not hasattr(settings, "ai_service_webhook_secret")


def test_replay_store_timeout_defaults_to_half_a_second():
    assert Settings(_env_file=None, app_environment="development").service_replay_timeout_seconds == 0.5


@pytest.mark.parametrize("value", [0.0, 0.01, 5.5, -1])
def test_replay_store_timeout_is_bounded(value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_environment="development", service_replay_timeout_seconds=value)

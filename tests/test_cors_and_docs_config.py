"""Explicit CORS and docs exposure (plan §8.4, §12; M6)."""

import pytest
from app.core.config import Settings

BOUNDARY = {
    "ai_service_url": "https://ai-service.internal",
    "backend_to_ai_secret": "b" * 40,
    "ai_to_backend_secret": "a" * 40,
    "auth_jwt_secret": "j" * 40,
}


def make(environment: str, **values) -> Settings:
    return Settings(_env_file=None, app_environment=environment, **{**BOUNDARY, **values})


def test_no_origins_by_default():
    assert make("production").cors_origins == []


def test_exact_https_origins_are_accepted_in_production():
    settings = make("production", cors_allowed_origins="https://app.build.example, https://admin.build.example/")
    assert settings.cors_origins == ["https://app.build.example", "https://admin.build.example"]


@pytest.mark.parametrize(
    "origins",
    ["*", "https://*.build.example", "http://app.build.example", "https://app.build.example/path", "app.build.example"],
)
def test_production_refuses_loose_origins(origins):
    with pytest.raises(ValueError, match="CORS"):
        make("production", cors_allowed_origins=origins)


def test_development_may_allow_a_local_http_origin():
    assert make("development", cors_allowed_origins="http://localhost:5173").cors_origins == ["http://localhost:5173"]


@pytest.mark.parametrize(
    "environment,override,expected",
    [
        ("development", None, True),
        ("testing", None, True),
        ("staging", None, False),
        ("production", None, False),
        ("production", True, True),
        ("development", False, False),
    ],
)
def test_docs_follow_the_environment_unless_set(environment, override, expected):
    values = {} if override is None else {"api_docs_enabled": override}
    assert make(environment, **values).docs_enabled is expected

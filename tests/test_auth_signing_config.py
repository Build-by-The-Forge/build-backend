import pytest

from app.core.config import Settings

STRONG = "s" * 32
OTHER_STRONG = "p" * 32


@pytest.fixture(autouse=True)
def no_ambient_jwt_env(monkeypatch):
    for name in (
        "AUTH_JWT_SECRET",
        "AUTH_JWT_KID",
        "AUTH_JWT_PREVIOUS_SECRET",
        "AUTH_JWT_PREVIOUS_KID",
    ):
        monkeypatch.delenv(name, raising=False)


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_strict_environments_refuse_to_start_without_a_signing_key(environment):
    with pytest.raises(ValueError, match="AUTH_JWT_SECRET is required"):
        make(app_environment=environment)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_strict_environments_accept_a_strong_key(environment):
    settings = make(app_environment=environment, auth_jwt_secret=STRONG)

    assert settings.jwt_verification_keys == {"primary": STRONG}


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_non_strict_environments_get_a_random_per_process_key(environment):
    first = make(app_environment=environment)
    second = make(app_environment=environment)

    assert len(first.auth_jwt_secret) >= 32
    assert first.auth_jwt_secret != second.auth_jwt_secret


@pytest.mark.parametrize("environment", ["development", "production"])
def test_short_keys_are_rejected_everywhere(environment):
    with pytest.raises(ValueError, match="at least 32 bytes"):
        make(app_environment=environment, auth_jwt_secret="too-short")


def test_rotation_accepts_current_and_previous_keys():
    settings = make(
        app_environment="production",
        auth_jwt_secret=STRONG,
        auth_jwt_kid="2026-10",
        auth_jwt_previous_secret=OTHER_STRONG,
        auth_jwt_previous_kid="2026-07",
    )

    assert settings.jwt_verification_keys == {"2026-10": STRONG, "2026-07": OTHER_STRONG}


def test_previous_key_requires_its_own_distinct_kid():
    with pytest.raises(ValueError, match="AUTH_JWT_PREVIOUS_KID is required"):
        make(auth_jwt_secret=STRONG, auth_jwt_previous_secret=OTHER_STRONG)
    with pytest.raises(ValueError, match="must differ"):
        make(
            auth_jwt_secret=STRONG,
            auth_jwt_previous_secret=OTHER_STRONG,
            auth_jwt_previous_kid="primary",
        )


def test_weak_previous_key_is_rejected():
    with pytest.raises(ValueError, match="AUTH_JWT_PREVIOUS_SECRET"):
        make(
            auth_jwt_secret=STRONG,
            auth_jwt_previous_secret="weak",
            auth_jwt_previous_kid="old",
        )

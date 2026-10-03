import os
import secrets
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where a missing or weak signing key must stop startup.
STRICT_ENVIRONMENTS = frozenset({"staging", "production"})
MIN_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    app_environment: str = Field(default="development")
    postgres_url: str = Field(default_factory=lambda: os.getenv("POSTGRES_URL", ""))
    redis_url: str = Field(default="redis://localhost:6379/0")
    debug: bool = Field(default=False)
    request_timeout_seconds: int = Field(default=30)
    tenant_header: str = Field(default="x-tenant-id")

    # AI Service Settings
    ai_service_url: str = Field(
        default_factory=lambda: os.getenv("AI_SERVICE_URL", "http://localhost:8001")
    )
    ai_service_api_key: str = Field(
        default_factory=lambda: os.getenv("AI_SERVICE_API_KEY", "build-ai-dev-secret-key")
    )
    ai_service_webhook_secret: str = Field(
        default_factory=lambda: os.getenv(
            "AI_SERVICE_WEBHOOK_SECRET", "build-ai-dev-webhook-secret"
        )
    )
    ai_service_timeout_seconds: int = Field(default=60)
    ai_service_max_retries: int = Field(default=3)

    # Access-token signing (HS256). The current key signs; the previous key,
    # if set, is still accepted for verification during a rotation.
    auth_jwt_secret: str | None = Field(default=None)
    auth_jwt_kid: str = Field(default="primary")
    auth_jwt_previous_secret: str | None = Field(default=None)
    auth_jwt_previous_kid: str | None = Field(default=None)
    auth_jwt_issuer: str = Field(default="build-backend")
    auth_jwt_audience: str = Field(default="build-api")
    auth_access_token_ttl_seconds: int = Field(default=900)
    # Absolute session lifetime: no refresh can extend a session past this.
    auth_session_absolute_ttl_seconds: int = Field(default=30 * 24 * 3600)
    # Idle lifetime of a refresh token; each rotation starts a new window.
    auth_refresh_idle_ttl_seconds: int = Field(default=14 * 24 * 3600)
    auth_password_reset_ttl_seconds: int = Field(default=3600)
    auth_email_verification_ttl_seconds: int = Field(default=24 * 3600)
    # What the auth rate limiter does when Redis is unreachable: "local" keeps
    # enforcing limits with per-process counters, "closed" refuses requests
    # with 503. There is deliberately no fail-open option.
    auth_rate_limit_failure_mode: Literal["local", "closed"] = Field(default="local")
    # Development only: also append outgoing email (with its one-time codes)
    # to this JSONL file. Ignored in staging/production.
    email_outbox_path: str | None = Field(default=None)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("app_environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"development", "testing", "staging", "production"}
        if value not in allowed:
            raise ValueError(f"app_environment must be one of {sorted(allowed)}")
        return value

    @field_validator("request_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError("request_timeout_seconds must be greater than 0")
        return value

    @field_validator("ai_service_timeout_seconds")
    @classmethod
    def validate_ai_timeout(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError("ai_service_timeout_seconds must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_jwt_signing_keys(self) -> "Settings":
        if not self.auth_jwt_secret:
            if self.app_environment in STRICT_ENVIRONMENTS:
                raise ValueError(
                    f"AUTH_JWT_SECRET is required when app_environment is {self.app_environment!r}"
                )
            # No usable default may live in the repository: development and
            # tests get a random per-process key instead.
            self.auth_jwt_secret = secrets.token_urlsafe(48)

        for name, secret in (
            ("AUTH_JWT_SECRET", self.auth_jwt_secret),
            ("AUTH_JWT_PREVIOUS_SECRET", self.auth_jwt_previous_secret),
        ):
            if secret is not None and len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
                raise ValueError(f"{name} must be at least {MIN_JWT_SECRET_BYTES} bytes")

        if self.auth_jwt_previous_secret is not None:
            if not self.auth_jwt_previous_kid:
                raise ValueError("AUTH_JWT_PREVIOUS_KID is required with AUTH_JWT_PREVIOUS_SECRET")
            if self.auth_jwt_previous_kid == self.auth_jwt_kid:
                raise ValueError("AUTH_JWT_PREVIOUS_KID must differ from AUTH_JWT_KID")

        if self.auth_access_token_ttl_seconds <= 0:
            raise ValueError("auth_access_token_ttl_seconds must be greater than 0")
        if self.auth_session_absolute_ttl_seconds <= 0:
            raise ValueError("auth_session_absolute_ttl_seconds must be greater than 0")
        if self.auth_refresh_idle_ttl_seconds <= 0:
            raise ValueError("auth_refresh_idle_ttl_seconds must be greater than 0")
        if self.auth_password_reset_ttl_seconds <= 0:
            raise ValueError("auth_password_reset_ttl_seconds must be greater than 0")
        if self.auth_email_verification_ttl_seconds <= 0:
            raise ValueError("auth_email_verification_ttl_seconds must be greater than 0")
        return self

    @property
    def jwt_verification_keys(self) -> dict[str, str]:
        """kid -> secret for every key currently accepted for verification."""
        keys = {self.auth_jwt_kid: self.auth_jwt_secret or ""}
        if self.auth_jwt_previous_secret and self.auth_jwt_previous_kid:
            keys[self.auth_jwt_previous_kid] = self.auth_jwt_previous_secret
        return keys

    @property
    def effective_postgres_url(self) -> str:
        if self.app_environment == "testing":
            return "sqlite+aiosqlite:///:memory:"
        return self.postgres_url


settings = Settings()

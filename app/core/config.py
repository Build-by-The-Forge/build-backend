import ipaddress
import os
import secrets
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where a missing or weak signing key must stop startup.
STRICT_ENVIRONMENTS = frozenset({"staging", "production"})
MIN_JWT_SECRET_BYTES = 32
MIN_SERVICE_SECRET_BYTES = 32
DEVELOPMENT_AI_SERVICE_URL = "http://localhost:8001"
# Values that have appeared in either repository or in the M3 design's test
# vectors. None of them may sign service requests in staging/production.
KNOWN_DEVELOPMENT_SERVICE_SECRETS = frozenset(
    {
        "dev-secret",
        "build-internal-service-secret",
        "build-ai-dev-secret-key",
        "build-ai-dev-webhook-secret",
        "test-only-backend-to-ai-secret-0123456789abcdef",
        "test-only-ai-to-backend-secret-fedcba9876543210",
    }
)


class Settings(BaseSettings):
    app_environment: str = Field(default="development")
    postgres_url: str = Field(default_factory=lambda: os.getenv("POSTGRES_URL", ""))
    redis_url: str = Field(default="redis://localhost:6379/0")
    debug: bool = Field(default=False)
    request_timeout_seconds: int = Field(default=30)

    # AI Service Settings
    # Required outside development/testing, where it defaults to localhost.
    ai_service_url: str = Field(default="")
    # BUILD Service Signature v1: one secret per direction, each with an
    # optional previous secret accepted (never used to sign) during rotation.
    # No defaults: required in staging/production, random per process in
    # testing, absent in development unless set.
    backend_to_ai_secret: str | None = Field(default=None)
    backend_to_ai_secret_previous: str | None = Field(default=None)
    ai_to_backend_secret: str | None = Field(default=None)
    ai_to_backend_secret_previous: str | None = Field(default=None)
    # Connect/read timeout (seconds) of the Redis replay store that guards
    # signed AI-service callbacks. A timeout fails closed (503); it never
    # admits the request. Default 0.5; allowed 0.05-5.0. Raise it only on
    # measured evidence from the deployment (see M3-08 follow-up report).
    service_replay_timeout_seconds: float = Field(default=0.5, ge=0.05, le=5.0)
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
    # Largest request body any route accepts (413 above it). JSON only today:
    # asset bytes never pass through the API.
    max_request_body_bytes: int = Field(default=1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    # Browser origins allowed to call the API, comma separated. Empty means no
    # CORS headers at all, so browsers refuse cross-origin calls (M6).
    cors_allowed_origins: str = Field(default="")
    # Interactive docs and the OpenAPI document; off in staging/production
    # unless explicitly enabled.
    api_docs_enabled: bool | None = Field(default=None)
    # Reverse proxies (IPs or CIDRs, comma separated) whose X-Forwarded-For
    # is believed. Empty: the direct peer is the client (M6).
    trusted_proxies: str = Field(default="")

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

    @model_validator(mode="after")
    def validate_service_boundary(self) -> "Settings":
        strict = self.app_environment in STRICT_ENVIRONMENTS
        if not self.ai_service_url:
            if strict:
                raise ValueError(
                    f"AI_SERVICE_URL is required when app_environment is {self.app_environment!r}"
                )
            self.ai_service_url = DEVELOPMENT_AI_SERVICE_URL
        parts = urlsplit(self.ai_service_url)
        # Requests are signed but responses are not (ruling E.4): outside
        # development the boundary must run over TLS.
        allowed = {"https"} if strict else {"http", "https"}
        if parts.scheme not in allowed or not parts.hostname:
            raise ValueError(
                f"AI_SERVICE_URL must be an absolute {' or '.join(sorted(allowed))} URL"
            )
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError(
                "AI_SERVICE_URL must not carry credentials, a query or a fragment"
            )

        if self.app_environment == "testing":
            # Single-process tests sign and verify with the same settings.
            self.backend_to_ai_secret = self.backend_to_ai_secret or secrets.token_urlsafe(48)
            self.ai_to_backend_secret = self.ai_to_backend_secret or secrets.token_urlsafe(48)

        directions = {
            "BACKEND_TO_AI": (self.backend_to_ai_secret, self.backend_to_ai_secret_previous),
            "AI_TO_BACKEND": (self.ai_to_backend_secret, self.ai_to_backend_secret_previous),
        }
        for prefix, (current, previous) in directions.items():
            if current is None and strict:
                raise ValueError(
                    f"{prefix}_SECRET is required when app_environment is {self.app_environment!r}"
                )
            if previous is not None and current is None:
                raise ValueError(f"{prefix}_SECRET_PREVIOUS requires {prefix}_SECRET")
            for name, value in (
                (f"{prefix}_SECRET", current),
                (f"{prefix}_SECRET_PREVIOUS", previous),
            ):
                if value is None:
                    continue
                if len(value.encode("utf-8")) < MIN_SERVICE_SECRET_BYTES:
                    raise ValueError(f"{name} must be at least {MIN_SERVICE_SECRET_BYTES} bytes")
                if strict and value in KNOWN_DEVELOPMENT_SERVICE_SECRETS:
                    raise ValueError(f"{name} is a known development value")

        # The directions never share a secret, including across a rotation.
        to_ai = {v for v in directions["BACKEND_TO_AI"] if v}
        to_backend = {v for v in directions["AI_TO_BACKEND"] if v}
        if to_ai & to_backend:
            raise ValueError("BACKEND_TO_AI and AI_TO_BACKEND secrets must differ")
        return self

    @model_validator(mode="after")
    def validate_cors_origins(self) -> "Settings":
        strict = self.app_environment in STRICT_ENVIRONMENTS
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            if origin == "*" or "*" in origin:
                raise ValueError("CORS_ALLOWED_ORIGINS must list exact origins, not wildcards")
            schemes = {"https"} if strict else {"http", "https"}
            if parts.scheme not in schemes or not parts.hostname or parts.path not in ("", "/"):
                raise ValueError(f"CORS origin {origin!r} must be a bare {' or '.join(sorted(schemes))} origin")
        return self

    @field_validator("trusted_proxies")
    @classmethod
    def validate_trusted_proxies(cls, value: str) -> str:
        for item in value.split(","):
            if item.strip():
                try:
                    ipaddress.ip_network(item.strip(), strict=False)
                except ValueError as exc:
                    raise ValueError(f"TRUSTED_PROXIES entry {item.strip()!r} is not an IP or CIDR") from exc
        return value

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [ipaddress.ip_network(i.strip(), strict=False) for i in self.trusted_proxies.split(",") if i.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def docs_enabled(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return self.app_environment not in STRICT_ENVIRONMENTS

    @property
    def ai_to_backend_verification_secrets(self) -> tuple[str, ...]:
        """Secrets accepted on inbound AI-service requests: current, then previous."""
        return tuple(
            s for s in (self.ai_to_backend_secret, self.ai_to_backend_secret_previous) if s
        )

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

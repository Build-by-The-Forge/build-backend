import os

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def effective_postgres_url(self) -> str:
        if self.app_environment == "testing":
            return "sqlite+aiosqlite:///:memory:"
        return self.postgres_url


settings = Settings()

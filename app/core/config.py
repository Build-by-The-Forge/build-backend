from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: str = Field(default="development")
    postgres_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/build"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    debug: bool = Field(default=False)
    request_timeout_seconds: int = Field(default=30)
    tenant_header: str = Field(default="x-tenant-id")

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

    @property
    def effective_postgres_url(self) -> str:
        if self.app_environment == "testing":
            return "sqlite+aiosqlite:///:memory:"
        return self.postgres_url


settings = Settings()

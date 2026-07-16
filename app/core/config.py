from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_PRODUCTION_VALUES: dict[str, frozenset[str]] = {
    "jwt_secret": frozenset(
        {
            "development-jwt-secret-change-before-production",
            "replace-with-at-least-32-random-characters",
        }
    ),
    "credential_pepper": frozenset(
        {
            "development-credential-pepper-change-before-production",
            "replace-with-another-long-random-secret",
        }
    ),
    "encryption_key": frozenset(
        {
            "6A0dKlz6yUenVGLWQVCuMBzK5z6PumvV1-0wI0Z7lGQ=",
            "replace-with-a-fernet-key",
        }
    ),
    "s3_access_key": frozenset({"minioadmin"}),
    "s3_secret_key": frozenset({"minioadmin"}),
}
_VALID_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Customer Service"
    env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_customer_service"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: SecretStr = SecretStr("minioadmin")
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_bucket: str = "ai-customer-service"
    s3_region: str = "us-east-1"
    jwt_secret: SecretStr = SecretStr("development-jwt-secret-change-before-production")
    credential_pepper: SecretStr = SecretStr(
        "development-credential-pepper-change-before-production"
    )
    encryption_key: SecretStr = SecretStr("6A0dKlz6yUenVGLWQVCuMBzK5z6PumvV1-0wI0Z7lGQ=")
    admin_access_token_minutes: int = Field(default=60, ge=5, le=1440)
    customer_token_minutes: int = Field(default=15, ge=1, le=60)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    allow_private_provider_urls: bool = False

    @field_validator("env")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _VALID_ENVIRONMENTS:
            allowed = ", ".join(sorted(_VALID_ENVIRONMENTS))
            raise ValueError(f"environment must be one of: {allowed}")
        return normalized

    @field_validator("jwt_secret", "credential_pepper")
    @classmethod
    def validate_long_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("secret must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if not self.is_production:
            return self

        if self.debug:
            raise ValueError("debug mode must be disabled in production")

        insecure_fields = [
            field_name
            for field_name, insecure_values in _INSECURE_PRODUCTION_VALUES.items()
            if getattr(self, field_name).get_secret_value() in insecure_values
        ]
        if insecure_fields:
            fields = ", ".join(sorted(insecure_fields))
            raise ValueError(f"production secrets must override development defaults: {fields}")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

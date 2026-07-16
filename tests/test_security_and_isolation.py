from typing import Self, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import MemoryRateLimiter, RedisRateLimiter


class RecordingPipeline:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def incr(self, key: str) -> Self:
        self.keys.append(key)
        return self

    def expire(self, key: str, _: int) -> Self:
        assert key == self.keys[-1]
        return self

    async def execute(self) -> tuple[int, bool]:
        return 1, True


class RecordingRedis:
    def __init__(self) -> None:
        self.recording_pipeline = RecordingPipeline()

    def pipeline(self, *, transaction: bool) -> RecordingPipeline:
        assert transaction
        return self.recording_pipeline


def _production_settings(**overrides: str) -> Settings:
    values = {
        "env": "production",
        "jwt_secret": "production-jwt-secret-with-at-least-32-characters",
        "credential_pepper": "production-credential-pepper-at-least-32-characters",
        "encryption_key": "GGfDio0hRrvCpiBZ8uMvz_JZN7o0NfGXqu3iArn4BSs=",
        "s3_access_key": "production-storage-access-key",
        "s3_secret_key": "production-storage-secret-key",
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.parametrize(
    ("field_name", "insecure_value"),
    [
        ("jwt_secret", "development-jwt-secret-change-before-production"),
        ("credential_pepper", "development-credential-pepper-change-before-production"),
        ("encryption_key", "6A0dKlz6yUenVGLWQVCuMBzK5z6PumvV1-0wI0Z7lGQ="),
        ("s3_access_key", "minioadmin"),
        ("s3_secret_key", "minioadmin"),
        ("jwt_secret", "replace-with-at-least-32-random-characters"),
        ("credential_pepper", "replace-with-another-long-random-secret"),
        ("encryption_key", "replace-with-a-fernet-key"),
    ],
)
def test_production_rejects_development_secret_defaults(
    field_name: str, insecure_value: str
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        _production_settings(**{field_name: insecure_value})


def test_production_environment_is_normalized_before_secret_validation() -> None:
    with pytest.raises(ValidationError, match="jwt_secret"):
        _production_settings(
            env=" Production ",
            jwt_secret="development-jwt-secret-change-before-production",
        )


def test_production_accepts_independent_secret_values() -> None:
    settings = _production_settings()

    assert settings.is_production


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError, match="debug mode must be disabled"):
        _production_settings(debug="true")


def test_development_allows_local_service_defaults() -> None:
    settings = Settings(
        env="development",
        jwt_secret="development-jwt-secret-change-before-production",
        credential_pepper="development-credential-pepper-change-before-production",
        encryption_key="6A0dKlz6yUenVGLWQVCuMBzK5z6PumvV1-0wI0Z7lGQ=",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )

    assert not settings.is_production


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError, match="environment must be one of"):
        _production_settings(env="prodution")


@pytest.mark.asyncio
async def test_rate_limit_keys_hide_subject_and_are_tenant_application_scoped() -> None:
    limiter = MemoryRateLimiter()
    tenant_a = uuid4()
    tenant_b = uuid4()
    application_a = uuid4()
    application_b = uuid4()
    external_user_id = "customer@example.com"

    await limiter.check(
        tenant_id=tenant_a,
        application_id=application_a,
        subject=external_user_id,
        limit=1,
    )
    await limiter.check(
        tenant_id=tenant_b,
        application_id=application_a,
        subject=external_user_id,
        limit=1,
    )
    await limiter.check(
        tenant_id=tenant_a,
        application_id=application_b,
        subject=external_user_id,
        limit=1,
    )

    assert len(limiter.counts) == 3
    assert all(external_user_id not in key for key in limiter.counts)
    assert any(str(tenant_a) in key and str(application_a) in key for key in limiter.counts)
    assert any(str(tenant_b) in key and str(application_a) in key for key in limiter.counts)
    assert any(str(tenant_a) in key and str(application_b) in key for key in limiter.counts)

    with pytest.raises(AppError) as exc_info:
        await limiter.check(
            tenant_id=tenant_a,
            application_id=application_a,
            subject=external_user_id,
            limit=1,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_redis_rate_limit_key_does_not_contain_external_user_id() -> None:
    redis = RecordingRedis()
    limiter = RedisRateLimiter(cast(Redis, redis))
    tenant_id = uuid4()
    application_id = uuid4()
    external_user_id = "customer:42@example.com"

    await limiter.check(
        tenant_id=tenant_id,
        application_id=application_id,
        subject=external_user_id,
        limit=10,
    )

    assert len(redis.recording_pipeline.keys) == 1
    key = redis.recording_pipeline.keys[0]
    assert key.startswith(f"rate:v1:{tenant_id}:{application_id}:")
    assert external_user_id not in key

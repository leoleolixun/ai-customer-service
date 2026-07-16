import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.identities.models import TenantRole

password_hash = PasswordHash.recommended()


@dataclass(frozen=True, slots=True)
class StaffPrincipal:
    user_id: UUID
    email: str
    is_platform_admin: bool
    tenant_id: UUID | None
    role: TenantRole | None
    auth_version: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerPrincipal:
    tenant_id: UUID
    application_id: UUID
    external_user_id: str
    scopes: tuple[str, ...]
    token_id: UUID


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def staff_auth_version(encoded_password: str) -> str:
    secret = get_settings().jwt_secret.get_secret_value().encode()
    return hmac.new(secret, encoded_password.encode(), hashlib.sha256).hexdigest()


def create_admin_access_token(principal: StaffPrincipal) -> tuple[str, datetime]:
    settings = get_settings()
    if principal.auth_version is None:
        raise ValueError("staff principal requires an authentication version")
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.admin_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(principal.user_id),
        "email": principal.email,
        "platform_admin": principal.is_platform_admin,
        "tenant_id": str(principal.tenant_id) if principal.tenant_id else None,
        "role": principal.role.value if principal.role else None,
        "auth_version": principal.auth_version,
        "aud": "admin",
        "iss": "ai-customer-service",
        "iat": datetime.now(UTC),
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    return token, expires_at


def create_customer_token(principal: CustomerPrincipal) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.customer_token_minutes)
    payload: dict[str, Any] = {
        "sub": principal.external_user_id,
        "tenant_id": str(principal.tenant_id),
        "application_id": str(principal.application_id),
        "scopes": list(principal.scopes),
        "aud": "customer",
        "iss": "ai-customer-service",
        "iat": datetime.now(UTC),
        "exp": expires_at,
        "jti": str(principal.token_id),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    return token, expires_at


def decode_token(token: str, *, audience: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=audience,
            issuer="ai-customer-service",
            options={"require": ["sub", "aud", "iss", "exp", "iat", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise AppError(
            status_code=401,
            code="invalid_token",
            title="Authentication failed",
            detail="The access token is invalid or expired.",
        ) from exc
    return dict(payload)


def generate_api_credential() -> tuple[str, str, str]:
    key_prefix = f"acs_{secrets.token_hex(8)}"
    secret = secrets.token_urlsafe(32)
    return key_prefix, secret, f"{key_prefix}.{secret}"


def hash_api_secret(secret: str) -> str:
    pepper = get_settings().credential_pepper.get_secret_value().encode()
    return hmac.new(pepper, secret.encode(), hashlib.sha256).hexdigest()


def verify_api_secret(secret: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_api_secret(secret), expected_hash)


def split_api_key(api_key: str) -> tuple[str, str]:
    prefix, separator, secret = api_key.partition(".")
    if not separator or not prefix.startswith("acs_") or not secret:
        raise AppError(
            status_code=401,
            code="invalid_api_key",
            title="Authentication failed",
            detail="The API key is invalid.",
        )
    return prefix, secret


def encrypt_secret(value: str) -> str:
    fernet = Fernet(get_settings().encryption_key.get_secret_value().encode())
    return fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    fernet = Fernet(get_settings().encryption_key.get_secret_value().encode())
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AppError(
            status_code=500,
            code="secret_decryption_failed",
            title="Configuration error",
            detail="A stored credential could not be decrypted.",
        ) from exc

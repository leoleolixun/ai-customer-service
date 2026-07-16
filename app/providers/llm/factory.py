from typing import NoReturn

from app.core.errors import AppError
from app.core.security import decrypt_secret
from app.domains.model_gateway.models import AIProviderAccount, ProviderKind
from app.providers.llm.base import ChatProvider, EmbeddingProvider
from app.providers.llm.fake import FakeChatProvider, FakeEmbeddingProvider
from app.providers.llm.openai_compatible import OpenAICompatibleProvider


def build_chat_provider(account: AIProviderAccount) -> ChatProvider:
    if account.kind == ProviderKind.FAKE:
        return FakeChatProvider()
    if account.kind == ProviderKind.OPENAI_COMPATIBLE:
        if account.base_url is None or account.api_key_ciphertext is None:
            _raise_invalid_provider_config()
        return OpenAICompatibleProvider(
            base_url=account.base_url,
            api_key=decrypt_secret(account.api_key_ciphertext),
        )
    _raise_invalid_provider_config()


def build_embedding_provider(account: AIProviderAccount) -> EmbeddingProvider:
    if account.kind == ProviderKind.FAKE:
        return FakeEmbeddingProvider()
    if account.kind == ProviderKind.OPENAI_COMPATIBLE:
        if account.base_url is None or account.api_key_ciphertext is None:
            _raise_invalid_provider_config()
        return OpenAICompatibleProvider(
            base_url=account.base_url,
            api_key=decrypt_secret(account.api_key_ciphertext),
        )
    _raise_invalid_provider_config()


def _raise_invalid_provider_config() -> NoReturn:
    raise AppError(
        status_code=500,
        code="invalid_provider_configuration",
        title="Provider configuration error",
        detail="The active model provider is not configured correctly.",
    )

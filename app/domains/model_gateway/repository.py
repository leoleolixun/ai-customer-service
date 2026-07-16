from typing import cast
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.model_gateway.models import (
    AIModelConfig,
    AIProviderAccount,
    ApplicationModelBinding,
    ModelPurpose,
    ModelStatus,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)


class ModelGatewayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_account(
        self,
        *,
        tenant_id: UUID | None,
        scope: ProviderScope,
        name: str,
        kind: ProviderKind,
        base_url: str | None,
        api_key_ciphertext: str | None,
    ) -> AIProviderAccount:
        account = AIProviderAccount(
            tenant_id=tenant_id,
            scope=scope,
            name=name,
            kind=kind,
            base_url=base_url,
            api_key_ciphertext=api_key_ciphertext,
        )
        self.session.add(account)
        await self.session.flush()
        return account

    async def list_accounts(self, tenant_id: UUID | None) -> list[AIProviderAccount]:
        if tenant_id is None:
            statement = select(AIProviderAccount).where(
                AIProviderAccount.scope == ProviderScope.PLATFORM
            )
        else:
            statement = select(AIProviderAccount).where(
                or_(
                    AIProviderAccount.tenant_id == tenant_id,
                    (AIProviderAccount.scope == ProviderScope.PLATFORM)
                    & (AIProviderAccount.status == ProviderStatus.READY),
                )
            )
        return list(
            await self.session.scalars(
                statement.order_by(AIProviderAccount.scope, AIProviderAccount.name)
            )
        )

    async def get_managed_account(
        self, *, account_id: UUID, tenant_id: UUID | None
    ) -> AIProviderAccount | None:
        statement = select(AIProviderAccount).where(AIProviderAccount.id == account_id)
        if tenant_id is None:
            statement = statement.where(AIProviderAccount.scope == ProviderScope.PLATFORM)
        else:
            statement = statement.where(AIProviderAccount.tenant_id == tenant_id)
        return cast(AIProviderAccount | None, await self.session.scalar(statement))

    async def get_available_account(
        self, *, account_id: UUID, tenant_id: UUID
    ) -> AIProviderAccount | None:
        statement = select(AIProviderAccount).where(
            AIProviderAccount.id == account_id,
            or_(
                AIProviderAccount.tenant_id == tenant_id,
                AIProviderAccount.scope == ProviderScope.PLATFORM,
            ),
        )
        return cast(AIProviderAccount | None, await self.session.scalar(statement))

    async def create_model_config(
        self,
        *,
        tenant_id: UUID,
        provider_account_id: UUID,
        name: str,
        model_name: str,
        purpose: ModelPurpose,
        embedding_dimension: int | None,
        temperature: float,
        max_tokens: int,
        input_price: int,
        output_price: int,
    ) -> AIModelConfig:
        config = AIModelConfig(
            tenant_id=tenant_id,
            provider_account_id=provider_account_id,
            name=name,
            model_name=model_name,
            purpose=purpose,
            embedding_dimension=embedding_dimension,
            temperature=temperature,
            max_tokens=max_tokens,
            input_price_micros_per_million=input_price,
            output_price_micros_per_million=output_price,
        )
        self.session.add(config)
        await self.session.flush()
        return config

    async def list_model_configs(self, tenant_id: UUID) -> list[AIModelConfig]:
        statement = (
            select(AIModelConfig)
            .where(AIModelConfig.tenant_id == tenant_id)
            .order_by(AIModelConfig.purpose, AIModelConfig.name)
        )
        return list(await self.session.scalars(statement))

    async def get_model_config(
        self, *, tenant_id: UUID, model_config_id: UUID
    ) -> AIModelConfig | None:
        statement = select(AIModelConfig).where(
            AIModelConfig.id == model_config_id,
            AIModelConfig.tenant_id == tenant_id,
        )
        return cast(AIModelConfig | None, await self.session.scalar(statement))

    async def activate_for_application(
        self,
        *,
        tenant_id: UUID,
        application_id: UUID,
        model_config: AIModelConfig,
    ) -> None:
        statement = select(ApplicationModelBinding).where(
            ApplicationModelBinding.tenant_id == tenant_id,
            ApplicationModelBinding.application_id == application_id,
            ApplicationModelBinding.purpose == model_config.purpose,
        )
        binding = cast(
            ApplicationModelBinding | None,
            await self.session.scalar(statement),
        )
        if binding is None:
            self.session.add(
                ApplicationModelBinding(
                    tenant_id=tenant_id,
                    application_id=application_id,
                    model_config_id=model_config.id,
                    purpose=model_config.purpose,
                )
            )
        else:
            binding.model_config_id = model_config.id
        model_config.status = ModelStatus.ACTIVE
        await self.session.flush()

    async def deactivate(self, *, tenant_id: UUID, model_config: AIModelConfig) -> None:
        await self.session.execute(
            delete(ApplicationModelBinding).where(
                ApplicationModelBinding.tenant_id == tenant_id,
                ApplicationModelBinding.model_config_id == model_config.id,
            )
        )
        model_config.status = ModelStatus.INACTIVE
        await self.session.flush()

    async def get_active_chat_configuration(
        self, *, tenant_id: UUID, application_id: UUID
    ) -> tuple[AIModelConfig, AIProviderAccount] | None:
        statement = (
            select(AIModelConfig, AIProviderAccount)
            .join(
                ApplicationModelBinding,
                ApplicationModelBinding.model_config_id == AIModelConfig.id,
            )
            .join(AIProviderAccount, AIProviderAccount.id == AIModelConfig.provider_account_id)
            .where(
                ApplicationModelBinding.tenant_id == tenant_id,
                ApplicationModelBinding.application_id == application_id,
                ApplicationModelBinding.purpose == ModelPurpose.CHAT,
                AIModelConfig.tenant_id == tenant_id,
                AIModelConfig.status == ModelStatus.ACTIVE,
                AIProviderAccount.status == ProviderStatus.READY,
                or_(
                    AIProviderAccount.tenant_id == tenant_id,
                    AIProviderAccount.scope == ProviderScope.PLATFORM,
                ),
            )
        )
        result = await self.session.execute(statement)
        return result.tuples().one_or_none()

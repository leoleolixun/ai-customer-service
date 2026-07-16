from typing import NoReturn
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.network import validate_external_http_url
from app.core.security import StaffPrincipal, decrypt_secret, encrypt_secret
from app.domains.applications.repository import ApplicationRepository
from app.domains.audit.repository import AuditRepository
from app.domains.identities.models import TenantRole
from app.domains.model_gateway.models import (
    AIModelConfig,
    AIProviderAccount,
    ModelPurpose,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.domains.model_gateway.repository import ModelGatewayRepository
from app.domains.model_gateway.schemas import (
    ModelActivateRequest,
    ModelConfigCreate,
    ProviderAccountCreate,
    ProviderAccountResponse,
    ProviderTestResponse,
)
from app.providers.llm.openai_compatible import OpenAICompatibleProvider


class ModelGatewayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ModelGatewayRepository(session)
        self.applications = ApplicationRepository(session)
        self.audit = AuditRepository(session)

    async def create_account(
        self,
        *,
        request: ProviderAccountCreate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> ProviderAccountResponse:
        tenant_id, scope = self._account_owner(actor)
        base_url = request.base_url
        api_key_ciphertext = None
        if request.kind == ProviderKind.OPENAI_COMPATIBLE:
            assert base_url is not None and request.api_key is not None
            base_url = await validate_external_http_url(base_url)
            api_key_ciphertext = encrypt_secret(request.api_key.get_secret_value())
        try:
            account = await self.repository.create_account(
                tenant_id=tenant_id,
                scope=scope,
                name=request.name.strip(),
                kind=request.kind,
                base_url=base_url,
                api_key_ciphertext=api_key_ciphertext,
            )
            await self._audit(actor, "provider_account.create", account.id, request_id)
            await self.session.commit()
            await self.session.refresh(account)
            return self._account_response(account)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="provider_account_name_conflict",
                title="Provider account already exists",
                detail="A provider account with this name already exists in this scope.",
            ) from exc

    async def list_accounts(self, actor: StaffPrincipal) -> list[ProviderAccountResponse]:
        tenant_id, _ = self._account_owner(actor)
        accounts = await self.repository.list_accounts(tenant_id)
        return [self._account_response(account) for account in accounts]

    async def test_account(
        self,
        *,
        account_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> ProviderTestResponse:
        tenant_id, _ = self._account_owner(actor)
        account = await self.repository.get_managed_account(
            account_id=account_id, tenant_id=tenant_id
        )
        if account is None:
            self._raise_account_not_found()
        if account.kind == ProviderKind.OPENAI_COMPATIBLE:
            assert account.base_url is not None and account.api_key_ciphertext is not None
            await validate_external_http_url(account.base_url)
            provider = OpenAICompatibleProvider(
                base_url=account.base_url,
                api_key=decrypt_secret(account.api_key_ciphertext),
            )
            await provider.test_connection()
        account.status = ProviderStatus.READY
        await self._audit(actor, "provider_account.test", account.id, request_id)
        await self.session.commit()
        return ProviderTestResponse(status=account.status, message="connection verified")

    async def create_model_config(
        self,
        *,
        request: ModelConfigCreate,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> AIModelConfig:
        tenant_id = self._tenant_admin_id(actor)
        account = await self.repository.get_available_account(
            account_id=request.provider_account_id, tenant_id=tenant_id
        )
        if account is None or account.status != ProviderStatus.READY:
            raise AppError(
                status_code=400,
                code="provider_account_not_ready",
                title="Provider account not ready",
                detail="The provider account must be available and pass its connection test.",
            )
        try:
            config = await self.repository.create_model_config(
                tenant_id=tenant_id,
                provider_account_id=account.id,
                name=request.name.strip(),
                model_name=request.model_name.strip(),
                purpose=request.purpose,
                embedding_dimension=request.embedding_dimension,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                input_price=request.input_price_micros_per_million,
                output_price=request.output_price_micros_per_million,
            )
            await self._audit(actor, "model_config.create", config.id, request_id)
            await self.session.commit()
            await self.session.refresh(config)
            return config
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                status_code=409,
                code="model_config_name_conflict",
                title="Model configuration already exists",
                detail="A model configuration with this name already exists in the tenant.",
            ) from exc

    async def list_model_configs(self, actor: StaffPrincipal) -> list[AIModelConfig]:
        return await self.repository.list_model_configs(self._tenant_admin_id(actor))

    async def activate(
        self,
        *,
        model_config_id: UUID,
        request: ModelActivateRequest,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> AIModelConfig:
        tenant_id = self._tenant_admin_id(actor)
        config = await self._get_model_config(tenant_id, model_config_id)
        if config.purpose != ModelPurpose.CHAT:
            raise AppError(
                status_code=400,
                code="embedding_binding_requires_knowledge_base",
                title="Knowledge base required",
                detail="Embedding models are activated when they are bound to a knowledge base.",
            )
        application = await self.applications.get_by_id(
            tenant_id=tenant_id, application_id=request.application_id
        )
        if application is None:
            raise AppError(
                status_code=404,
                code="application_not_found",
                title="Application not found",
                detail="The requested application does not exist in this tenant.",
            )
        await self.repository.activate_for_application(
            tenant_id=tenant_id,
            application_id=application.id,
            model_config=config,
        )
        await self._audit(actor, "model_config.activate", config.id, request_id)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def deactivate(
        self,
        *,
        model_config_id: UUID,
        actor: StaffPrincipal,
        request_id: str | None,
    ) -> AIModelConfig:
        tenant_id = self._tenant_admin_id(actor)
        config = await self._get_model_config(tenant_id, model_config_id)
        if config.purpose == ModelPurpose.EMBEDDING:
            raise AppError(
                status_code=409,
                code="embedding_model_managed_by_knowledge_base",
                title="Embedding model is managed by knowledge bases",
                detail=(
                    "Embedding model versions are immutable in V1.0. "
                    "Create and rebind a new knowledge base to replace one."
                ),
            )
        await self.repository.deactivate(tenant_id=tenant_id, model_config=config)
        await self._audit(actor, "model_config.deactivate", config.id, request_id)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def _get_model_config(self, tenant_id: UUID, model_config_id: UUID) -> AIModelConfig:
        config = await self.repository.get_model_config(
            tenant_id=tenant_id, model_config_id=model_config_id
        )
        if config is None:
            raise AppError(
                status_code=404,
                code="model_config_not_found",
                title="Model configuration not found",
                detail="The requested model configuration does not exist in this tenant.",
            )
        return config

    async def _audit(
        self, actor: StaffPrincipal, action: str, resource_id: UUID, request_id: str | None
    ) -> None:
        await self.audit.add(
            tenant_id=actor.tenant_id,
            actor_type="staff",
            actor_id=str(actor.user_id),
            action=action,
            resource_type="model_gateway",
            resource_id=str(resource_id),
            request_id=request_id,
        )

    @staticmethod
    def _account_owner(actor: StaffPrincipal) -> tuple[UUID | None, ProviderScope]:
        if actor.is_platform_admin and actor.tenant_id is None:
            return None, ProviderScope.PLATFORM
        if actor.tenant_id is not None and actor.role == TenantRole.TENANT_ADMIN:
            return actor.tenant_id, ProviderScope.TENANT
        raise AppError(
            status_code=403,
            code="ai_manager_required",
            title="Forbidden",
            detail="A platform or tenant AI administrator session is required.",
        )

    @staticmethod
    def _tenant_admin_id(actor: StaffPrincipal) -> UUID:
        if actor.tenant_id is None or actor.role != TenantRole.TENANT_ADMIN:
            raise AppError(
                status_code=403,
                code="tenant_admin_required",
                title="Forbidden",
                detail="A tenant administrator session is required.",
            )
        return actor.tenant_id

    @staticmethod
    def _account_response(account: AIProviderAccount) -> ProviderAccountResponse:
        return ProviderAccountResponse(
            id=account.id,
            tenant_id=account.tenant_id,
            scope=account.scope,
            name=account.name,
            kind=account.kind,
            base_url=account.base_url,
            has_api_key=account.api_key_ciphertext is not None,
            status=account.status,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    @staticmethod
    def _raise_account_not_found() -> NoReturn:
        raise AppError(
            status_code=404,
            code="provider_account_not_found",
            title="Provider account not found",
            detail="The requested provider account does not exist in this scope.",
        )

from uuid import UUID

from fastapi import APIRouter, Request, status

from app.api.dependencies import AIManagerDependency, SessionDependency, TenantAdminDependency
from app.domains.model_gateway.schemas import (
    ModelActivateRequest,
    ModelConfigCreate,
    ModelConfigResponse,
    ProviderAccountCreate,
    ProviderAccountResponse,
    ProviderAccountUpdate,
    ProviderTestResponse,
)
from app.domains.model_gateway.service import ModelGatewayService

router = APIRouter(prefix="/admin/ai", tags=["model-gateway"])


@router.post(
    "/provider-accounts",
    response_model=ProviderAccountResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProviderAccount",
)
async def create_provider_account(
    body: ProviderAccountCreate,
    request: Request,
    actor: AIManagerDependency,
    session: SessionDependency,
) -> ProviderAccountResponse:
    return await ModelGatewayService(session).create_account(
        request=body, actor=actor, request_id=request.state.request_id
    )


@router.get(
    "/provider-accounts",
    response_model=list[ProviderAccountResponse],
    operation_id="listProviderAccounts",
)
async def list_provider_accounts(
    actor: AIManagerDependency,
    session: SessionDependency,
) -> list[ProviderAccountResponse]:
    return await ModelGatewayService(session).list_accounts(actor)


@router.patch(
    "/provider-accounts/{account_id}",
    response_model=ProviderAccountResponse,
    operation_id="updateProviderAccount",
)
async def update_provider_account(
    account_id: UUID,
    body: ProviderAccountUpdate,
    request: Request,
    actor: AIManagerDependency,
    session: SessionDependency,
) -> ProviderAccountResponse:
    return await ModelGatewayService(session).update_account(
        account_id=account_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.delete(
    "/provider-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteProviderAccount",
)
async def delete_provider_account(
    account_id: UUID,
    request: Request,
    actor: AIManagerDependency,
    session: SessionDependency,
) -> None:
    await ModelGatewayService(session).delete_account(
        account_id=account_id,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.post(
    "/provider-accounts/{account_id}/test",
    response_model=ProviderTestResponse,
    operation_id="testProviderAccount",
)
async def test_provider_account(
    account_id: UUID,
    request: Request,
    actor: AIManagerDependency,
    session: SessionDependency,
) -> ProviderTestResponse:
    return await ModelGatewayService(session).test_account(
        account_id=account_id,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.post(
    "/model-configs",
    response_model=ModelConfigResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createModelConfig",
)
async def create_model_config(
    body: ModelConfigCreate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> ModelConfigResponse:
    config = await ModelGatewayService(session).create_model_config(
        request=body, actor=actor, request_id=request.state.request_id
    )
    return ModelConfigResponse.model_validate(config)


@router.get(
    "/model-configs",
    response_model=list[ModelConfigResponse],
    operation_id="listModelConfigs",
)
async def list_model_configs(
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> list[ModelConfigResponse]:
    configs = await ModelGatewayService(session).list_model_configs(actor)
    return [ModelConfigResponse.model_validate(config) for config in configs]


@router.post(
    "/model-configs/{model_config_id}/activate",
    response_model=ModelConfigResponse,
    operation_id="activateModelConfig",
)
async def activate_model_config(
    model_config_id: UUID,
    body: ModelActivateRequest,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> ModelConfigResponse:
    config = await ModelGatewayService(session).activate(
        model_config_id=model_config_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )
    return ModelConfigResponse.model_validate(config)


@router.post(
    "/model-configs/{model_config_id}/deactivate",
    response_model=ModelConfigResponse,
    operation_id="deactivateModelConfig",
)
async def deactivate_model_config(
    model_config_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> ModelConfigResponse:
    config = await ModelGatewayService(session).deactivate(
        model_config_id=model_config_id,
        actor=actor,
        request_id=request.state.request_id,
    )
    return ModelConfigResponse.model_validate(config)

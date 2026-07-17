from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status

from app.api.dependencies import AgentDependency, SessionDependency, TenantAdminDependency
from app.domains.applications.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    CredentialCreate,
    CredentialCreatedResponse,
    CredentialResponse,
    CustomerTokenRequest,
    CustomerTokenResponse,
)
from app.domains.applications.service import ApplicationService, CustomerTokenService

router = APIRouter(tags=["applications"])


@router.post(
    "/admin/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createApplication",
)
async def create_application(
    body: ApplicationCreate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> ApplicationResponse:
    assert actor.tenant_id is not None
    application = await ApplicationService(session).create(
        tenant_id=actor.tenant_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )
    return ApplicationResponse.model_validate(application)


@router.get(
    "/admin/applications",
    response_model=list[ApplicationResponse],
    operation_id="listApplications",
)
async def list_applications(
    actor: AgentDependency,
    session: SessionDependency,
) -> list[ApplicationResponse]:
    assert actor.tenant_id is not None
    applications = await ApplicationService(session).list(actor.tenant_id)
    return [ApplicationResponse.model_validate(application) for application in applications]


@router.patch(
    "/admin/applications/{application_id}",
    response_model=ApplicationResponse,
    operation_id="updateApplication",
)
async def update_application(
    application_id: UUID,
    body: ApplicationUpdate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> ApplicationResponse:
    assert actor.tenant_id is not None
    application = await ApplicationService(session).update(
        tenant_id=actor.tenant_id,
        application_id=application_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )
    return ApplicationResponse.model_validate(application)


@router.post(
    "/admin/applications/{application_id}/credentials",
    response_model=CredentialCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createApplicationCredential",
)
async def create_credential(
    application_id: UUID,
    body: CredentialCreate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> CredentialCreatedResponse:
    assert actor.tenant_id is not None
    return await ApplicationService(session).create_credential(
        tenant_id=actor.tenant_id,
        application_id=application_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.get(
    "/admin/applications/{application_id}/credentials",
    response_model=list[CredentialResponse],
    operation_id="listApplicationCredentials",
)
async def list_credentials(
    application_id: UUID,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> list[CredentialResponse]:
    assert actor.tenant_id is not None
    credentials = await ApplicationService(session).list_credentials(
        tenant_id=actor.tenant_id,
        application_id=application_id,
    )
    return [CredentialResponse.model_validate(credential) for credential in credentials]


@router.delete(
    "/admin/applications/{application_id}/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="revokeApplicationCredential",
)
async def revoke_credential(
    application_id: UUID,
    credential_id: UUID,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> Response:
    assert actor.tenant_id is not None
    await ApplicationService(session).revoke_credential(
        tenant_id=actor.tenant_id,
        application_id=application_id,
        credential_id=credential_id,
        actor=actor,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/customer-tokens",
    response_model=CustomerTokenResponse,
    operation_id="createCustomerToken",
)
async def create_customer_token(
    body: CustomerTokenRequest,
    request: Request,
    session: SessionDependency,
    api_key: Annotated[str, Header(alias="X-API-Key")],
    origin: Annotated[str | None, Header(alias="Origin")] = None,
) -> CustomerTokenResponse:
    return await CustomerTokenService(session).issue(
        api_key=api_key,
        external_user_id=body.external_user_id,
        origin=origin,
        request_id=request.state.request_id,
    )

from uuid import UUID

from fastapi import APIRouter, Request, status

from app.api.dependencies import PlatformAdminDependency, SessionDependency
from app.domains.identities.models import TenantRole
from app.domains.identities.schemas import MemberCreate, MemberResponse, TenantAdminCreate
from app.domains.identities.service import MemberService
from app.domains.tenants.schemas import TenantCreate, TenantResponse, TenantUpdate
from app.domains.tenants.service import TenantService

router = APIRouter(prefix="/platform/tenants", tags=["platform-tenants"])


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createTenant",
)
async def create_tenant(
    body: TenantCreate,
    request: Request,
    actor: PlatformAdminDependency,
    session: SessionDependency,
) -> TenantResponse:
    tenant = await TenantService(session).create(body, actor, request.state.request_id)
    return TenantResponse.model_validate(tenant)


@router.get("", response_model=list[TenantResponse], operation_id="listTenants")
async def list_tenants(
    _: PlatformAdminDependency,
    session: SessionDependency,
) -> list[TenantResponse]:
    tenants = await TenantService(session).list_all()
    return [TenantResponse.model_validate(tenant) for tenant in tenants]


@router.patch("/{tenant_id}", response_model=TenantResponse, operation_id="updateTenant")
async def update_tenant(
    tenant_id: UUID,
    body: TenantUpdate,
    request: Request,
    actor: PlatformAdminDependency,
    session: SessionDependency,
) -> TenantResponse:
    tenant = await TenantService(session).update(tenant_id, body, actor, request.state.request_id)
    return TenantResponse.model_validate(tenant)


@router.post(
    "/{tenant_id}/admins",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createTenantAdministrator",
)
async def create_tenant_administrator(
    tenant_id: UUID,
    body: TenantAdminCreate,
    request: Request,
    actor: PlatformAdminDependency,
    session: SessionDependency,
) -> MemberResponse:
    return await MemberService(session).create(
        tenant_id=tenant_id,
        request=MemberCreate(
            email=body.email,
            display_name=body.display_name,
            temporary_password=body.temporary_password,
            role=TenantRole.TENANT_ADMIN,
        ),
        actor=actor,
        request_id=request.state.request_id,
    )

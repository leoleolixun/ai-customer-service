from uuid import UUID

from fastapi import APIRouter, Request, status

from app.api.dependencies import SessionDependency, TenantAdminDependency
from app.domains.identities.schemas import MemberCreate, MemberResponse, MemberUpdate
from app.domains.identities.service import MemberService

router = APIRouter(prefix="/admin/members", tags=["tenant-members"])


@router.post(
    "",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createTenantMember",
)
async def create_member(
    body: MemberCreate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> MemberResponse:
    assert actor.tenant_id is not None
    return await MemberService(session).create(
        tenant_id=actor.tenant_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )


@router.get("", response_model=list[MemberResponse], operation_id="listTenantMembers")
async def list_members(
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> list[MemberResponse]:
    assert actor.tenant_id is not None
    return await MemberService(session).list(actor.tenant_id)


@router.patch("/{membership_id}", response_model=MemberResponse, operation_id="updateTenantMember")
async def update_member(
    membership_id: UUID,
    body: MemberUpdate,
    request: Request,
    actor: TenantAdminDependency,
    session: SessionDependency,
) -> MemberResponse:
    assert actor.tenant_id is not None
    return await MemberService(session).update(
        tenant_id=actor.tenant_id,
        membership_id=membership_id,
        request=body,
        actor=actor,
        request_id=request.state.request_id,
    )

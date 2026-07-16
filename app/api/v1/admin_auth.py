from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import CurrentStaffDependency, SessionDependency
from app.domains.identities.schemas import (
    AdminLoginRequest,
    AdminMeResponse,
    AdminTokenResponse,
    PasswordChangeRequest,
)
from app.domains.identities.service import AdminAuthService

router = APIRouter(prefix="/admin", tags=["admin-auth"])


@router.post("/auth/login", response_model=AdminTokenResponse, operation_id="adminLogin")
async def login(body: AdminLoginRequest, session: SessionDependency) -> AdminTokenResponse:
    return await AdminAuthService(session).login(body)


@router.get("/me", response_model=AdminMeResponse, operation_id="getAdminMe")
async def me(current: CurrentStaffDependency) -> AdminMeResponse:
    return AdminMeResponse(
        id=current.user_id,
        email=current.email,
        is_platform_admin=current.is_platform_admin,
        tenant_id=current.tenant_id,
        role=current.role,
    )


@router.post(
    "/auth/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="changeAdminPassword",
)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    current: CurrentStaffDependency,
    session: SessionDependency,
) -> Response:
    await AdminAuthService(session).change_password(
        actor=current,
        request=body,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

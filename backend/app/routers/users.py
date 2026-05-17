# ================================================================
# NexusCare — app/routers/users.py
# Hospital-scoped user management routes and the small per-hospital
# role listing endpoint. Every route uses the JWT's hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
# ================================================================

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import UserRole
from app.database import get_db
from app.dependencies.audit import get_request_metadata
from app.dependencies.auth import (
    get_current_membership,
    get_current_user,
    require_role,
)
from app.dependencies.hospital import get_hospital_id
from app.models.hospital import Role
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.audit import RequestMetadata
from app.schemas.common import MessageResponse
from app.schemas.role import RoleResponse
from app.schemas.user import (
    MembershipUpdateRequest,
    UserInviteRequest,
    UserInviteResponse,
    UserListResponse,
    UserResponse,
    UserSelfUpdateRequest,
    UserUpdateRequest,
)
from app.services import user as user_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/users", tags=["Users"])
roles_router = APIRouter(prefix="/api/v1/roles", tags=["Roles"])


# ----------------------------------------------------------------
# ROLES (helper endpoint so the invite UI can populate role_id)
# ----------------------------------------------------------------

@roles_router.get("", response_model=list[RoleResponse])
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Returns roles this hospital may assign: its own roles + system roles."""
    result = await db.execute(
        select(Role)
        .where(or_(Role.hospital_id == hospital_id, Role.hospital_id.is_(None)))
        .order_by(Role.name.asc())
    )
    return list(result.scalars().all())


# ----------------------------------------------------------------
# INVITE
# ----------------------------------------------------------------

@router.post(
    "/invite",
    response_model=UserInviteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def invite_user(
    payload: UserInviteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await user_service.invite_user_to_hospital(
        db, hospital_id, payload, current_user.id
    )
    return UserInviteResponse(**result)


# ----------------------------------------------------------------
# LIST USERS
# ----------------------------------------------------------------

@router.get("", response_model=UserListResponse)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    role: Optional[str] = Query(default=None, description="Filter by role name"),
):
    return await user_service.list_users(
        db, hospital_id, pagination.page, pagination.size, role
    )


# ----------------------------------------------------------------
# /me — own profile update (read still lives at /auth/me)
# ----------------------------------------------------------------

@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserSelfUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return await user_service.update_user_profile(db, current_user, payload)


# ----------------------------------------------------------------
# /{user_id}
# ----------------------------------------------------------------

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await user_service.get_user_in_hospital(db, hospital_id, user_id)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await user_service.update_user_profile_as_admin(
        db, hospital_id, user_id, payload
    )


@router.patch(
    "/{user_id}/membership",
    response_model=MessageResponse,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def update_membership(
    user_id: uuid.UUID,
    payload: MembershipUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    await user_service.update_membership(
        db, hospital_id, user_id, payload, current_user.id
    )
    return MessageResponse(message="Membership updated.")


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def remove_user_from_hospital(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    request_meta: Annotated[RequestMetadata, Depends(get_request_metadata)],
):
    await user_service.soft_delete_membership(
        db,
        hospital_id,
        user_id,
        current_user.id,
        membership.id,
        request_meta=request_meta,
    )

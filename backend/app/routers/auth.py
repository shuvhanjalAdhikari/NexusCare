# ================================================================
# NexusCare — app/routers/auth.py
# Two-step login (Slack-style), workspace selection, /me, change-password.
# ================================================================

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import (
    get_current_membership,
    get_current_user,
    get_selection_token,
)
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    SelectionTokenPayload,
    SelectionTokenResponse,
    TokenResponse,
    WorkspaceSelectRequest,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserMeResponse
from app.services import auth as auth_service


router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


# ----------------------------------------------------------------
# STEP 1: LOGIN
# ----------------------------------------------------------------

@router.post("/login", response_model=SelectionTokenResponse)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await auth_service.authenticate_user(db, payload.email, payload.password)
    memberships = await auth_service.list_memberships(db, user.id)
    return SelectionTokenResponse(
        selection_token=auth_service.issue_selection_token(user),
        memberships=auth_service.build_membership_options(memberships),
    )


@router.post("/login-form", response_model=SelectionTokenResponse)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Form-encoded login for Swagger UI's Authorize button. The OAuth2
    password flow uses 'username' for the user identifier — we treat
    it as the email. Behaviour is otherwise identical to /login.
    """
    user = await auth_service.authenticate_user(db, form.username, form.password)
    memberships = await auth_service.list_memberships(db, user.id)
    return SelectionTokenResponse(
        selection_token=auth_service.issue_selection_token(user),
        memberships=auth_service.build_membership_options(memberships),
    )


# ----------------------------------------------------------------
# STEP 2: SELECT WORKSPACE
# ----------------------------------------------------------------

@router.post("/select-workspace", response_model=TokenResponse)
async def select_workspace(
    payload: WorkspaceSelectRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[SelectionTokenPayload, Depends(get_selection_token)],
):
    """
    Consumes a Bearer-delivered selection token and returns the full
    scoped access token. The dependency has already validated that
    type == "selection"; we only need the user_id (sub) here.
    """
    return await auth_service.select_workspace(db, token.sub, payload.hospital_id)


# ----------------------------------------------------------------
# CHANGE PASSWORD
# ----------------------------------------------------------------

@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: PasswordChangeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    await auth_service.change_password(
        db, current_user, payload.current_password, payload.new_password
    )
    return MessageResponse(message="Password updated.")


# ----------------------------------------------------------------
# CURRENT USER
# ----------------------------------------------------------------

@router.get("/me", response_model=UserMeResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        system_role=current_user.system_role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        current_hospital_id=membership.hospital_id,
        current_membership_id=membership.id,
        current_role=membership.role.name,
    )

# ================================================================
# NexusCare — app/schemas/user.py
# User read + management schemas. Used by /auth/me, /users, and admin
# invite flows. hospital_id is never accepted from the body — it always
# comes from the JWT.
# ================================================================

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.email import normalize_email
from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# USER RESPONSE
# ----------------------------------------------------------------

class UserResponse(BaseModel):
    """Public-facing user shape. No password hash, no audit timestamps beyond created_at."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    system_role: Optional[str] = None
    is_active: bool
    created_at: datetime


class UserMeResponse(UserResponse):
    """Adds the active hospital + role from the current JWT context."""

    current_hospital_id: UUID
    current_membership_id: UUID
    current_role: str


# ----------------------------------------------------------------
# USER LISTING (per-hospital)
# ----------------------------------------------------------------

class UserListItem(BaseModel):
    """One row in the per-hospital user list. Joins users + hospital_memberships + roles."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool                # user-level (global)
    membership_active: bool        # membership-level (this hospital)
    joined_at: datetime            # membership.created_at


UserListResponse = PagedResponse[UserListItem]


# ----------------------------------------------------------------
# INVITE A NEW MEMBER
# ----------------------------------------------------------------

class UserInviteRequest(BaseModel):
    """Body for POST /api/v1/users/invite (hospital admin only)."""

    email: EmailStr = Field(max_length=150)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role_id: UUID  # must reference a role visible to this hospital (own role or system role)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return normalize_email(v) if isinstance(v, str) else v


class UserInviteResponse(BaseModel):
    """
    Response from POST /api/v1/users/invite.

    Two outcomes:
      * Brand-new account — invite_token is set; the invitee must call
        /auth/accept-invite with this token to set their password.
      * Existing platform user added to this hospital — invite_token is None
        and requires_password=False; the user can log in immediately with
        their existing credentials.
    """

    user_id: UUID
    email: EmailStr
    invite_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    requires_password: bool
    message: str


# ----------------------------------------------------------------
# PROFILE UPDATES
# ----------------------------------------------------------------

class UserUpdateRequest(BaseModel):
    """Body for PATCH /api/v1/users/{user_id} (hospital admin only)."""

    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    avatar_url: Optional[str] = Field(default=None, max_length=2000)


class UserSelfUpdateRequest(UserUpdateRequest):
    """Body for PATCH /api/v1/users/me. Same fields, separate type for clarity."""


# ----------------------------------------------------------------
# MEMBERSHIP UPDATE
# ----------------------------------------------------------------

class MembershipUpdateRequest(BaseModel):
    """Body for PATCH /api/v1/users/{user_id}/membership (hospital admin only)."""

    role_id: Optional[UUID] = None
    is_active: Optional[bool] = None

# ================================================================
# NexusCare — app/schemas/auth.py
# Login, workspace selection, token, password change, invite,
# and password-reset schemas.
# ================================================================

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.email import normalize_email


# ----------------------------------------------------------------
# LOGIN
# ----------------------------------------------------------------

class LoginRequest(BaseModel):
    """Step 1: authenticate user. Returns selection token + memberships."""

    # max_length is belt-and-suspenders: EmailStr does the RFC validation,
    # but the explicit bound stops absurdly long strings before the validator runs.
    email: EmailStr = Field(max_length=150)
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return normalize_email(v) if isinstance(v, str) else v


# ----------------------------------------------------------------
# MEMBERSHIP OPTIONS (returned alongside selection token)
# ----------------------------------------------------------------

class MembershipOption(BaseModel):
    """One workspace the authenticated user may select."""

    model_config = ConfigDict(from_attributes=True)

    hospital_id: UUID
    hospital_name: str
    hospital_slug: str
    role: str
    is_active: bool


class SelectionTokenResponse(BaseModel):
    """Response body for POST /auth/login."""

    selection_token: str
    memberships: list[MembershipOption]


# ----------------------------------------------------------------
# WORKSPACE SELECTION
# ----------------------------------------------------------------

class WorkspaceSelectRequest(BaseModel):
    """Step 2: pick a hospital from the memberships list."""

    hospital_id: UUID


class SelectionTokenPayload(BaseModel):
    """Decoded claims from a selection token. Bearer-delivered, not in body."""

    sub: UUID
    type: str
    exp: int


class TokenResponse(BaseModel):
    """Final access token, returned by POST /auth/select-workspace."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ----------------------------------------------------------------
# PASSWORD CHANGE
# ----------------------------------------------------------------

class PasswordChangeRequest(BaseModel):
    """Body for POST /auth/change-password. Current password required."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


# ----------------------------------------------------------------
# INVITE ACCEPTANCE
# ----------------------------------------------------------------

class AcceptInviteRequest(BaseModel):
    """Body for POST /auth/accept-invite. Sets the password for an invited user."""

    invite_token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)


# ----------------------------------------------------------------
# PASSWORD RESET (self-service)
# ----------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    """Body for POST /auth/forgot-password. Always returns a generic 200."""

    email: EmailStr = Field(max_length=150)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return normalize_email(v) if isinstance(v, str) else v


class ResetPasswordRequest(BaseModel):
    """Body for POST /auth/reset-password."""

    reset_token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)

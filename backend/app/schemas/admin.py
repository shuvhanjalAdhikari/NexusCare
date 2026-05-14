# ================================================================
# NexusCare — app/schemas/admin.py
# Super-admin (platform-level) schemas. Used by /api/v1/admin/* only.
# ================================================================

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.email import normalize_email


# ----------------------------------------------------------------
# CREATE HOSPITAL (+ bootstrap admin user)
# ----------------------------------------------------------------

class HospitalCreateRequest(BaseModel):
    """
    Body for POST /api/v1/admin/hospitals.

    Provisions the tenant, seeds the 7 built-in per-hospital roles
    (see services/admin.py), and creates the first hospital_admin
    account in one transaction. The admin sets their password by
    accepting the returned invite token via /auth/accept-invite.
    """

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    timezone: str = Field(default="UTC", max_length=60)

    admin_email: EmailStr = Field(max_length=150)
    admin_first_name: str = Field(min_length=1, max_length=100)
    admin_last_name: str = Field(min_length=1, max_length=100)

    @field_validator("admin_email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class HospitalSummary(BaseModel):
    """Hospital fields returned as part of the create response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    timezone: str
    status: str
    created_at: datetime


class HospitalCreateResponse(BaseModel):
    """Response from POST /api/v1/admin/hospitals."""

    hospital: HospitalSummary
    admin_user_id: UUID
    admin_email: EmailStr
    invite_token: str
    invite_expires_at: datetime

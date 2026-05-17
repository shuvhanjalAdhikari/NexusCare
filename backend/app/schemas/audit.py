# ================================================================
# NexusCare — app/schemas/audit.py
# Pydantic schemas for the audit trail.
#
# Canonical column names: the audit_logs table uses resource_type /
# resource_id (NOT entity_type / entity_id) and the two structured
# JSONB fields old_value / new_value (there is no `changes` or
# `metadata` column). The schemas below mirror those names exactly.
# ================================================================

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# REQUEST METADATA
# ----------------------------------------------------------------

class RequestMetadata(BaseModel):
    """
    The caller's network context, captured by the get_request_metadata
    dependency and threaded into log_audit.

    Both fields are None for system / background actions that run
    without an HTTP request (e.g. scheduled status sweeps).
    """

    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# ----------------------------------------------------------------
# AUDIT-READ SCOPE
# ----------------------------------------------------------------

class AuditAccess(BaseModel):
    """
    Resolved audit-read scope produced by the require_audit_reader
    dependency.

    * super_admin    — is_super_admin=True, hospital_id=None: reads
      every hospital's logs (cross-tenant).
    * hospital_admin — is_super_admin=False, hospital_id set: reads
      only that hospital's logs.
    """

    is_super_admin: bool
    hospital_id: Optional[UUID] = None


# ----------------------------------------------------------------
# RESPONSE SCHEMAS
# ----------------------------------------------------------------

class AuditLogResponse(BaseModel):
    """
    One audit_logs row as returned to an admin.

    hospital_id / user_id / membership_id are nullable: login,
    login_failed, and account_locked events occur before workspace
    selection and so carry no hospital or membership context.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    membership_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[UUID] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    @field_validator("ip_address", mode="before")
    @classmethod
    def _ip_to_str(cls, value: Any) -> Optional[str]:
        """The INET column is read back as an ipaddress.IPv4Address /
        IPv6Address object; coerce it to a plain string for the response."""
        return str(value) if value is not None else None


AuditLogListResponse = PagedResponse[AuditLogResponse]

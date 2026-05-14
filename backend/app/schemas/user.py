# ================================================================
# NexusCare — app/schemas/user.py
# Read-side user schemas. Create/update schemas land in a later phase.
# ================================================================

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ----------------------------------------------------------------
# USER RESPONSE
# ----------------------------------------------------------------

class UserResponse(BaseModel):
    """Public-facing user shape. No password hash, no audit timestamps beyond created_at."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
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

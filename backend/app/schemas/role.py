# ================================================================
# NexusCare — app/schemas/role.py
# Read-side role schema used by GET /api/v1/roles. Roles are created
# by the hospital-bootstrap flow (see services/admin.py); we do not
# expose a create endpoint in this phase.
# ================================================================

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RoleResponse(BaseModel):
    """One role visible to the current hospital (own role or system role)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    is_custom: bool

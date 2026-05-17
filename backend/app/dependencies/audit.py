# ================================================================
# NexusCare — app/dependencies/audit.py
# FastAPI dependencies for the audit trail:
#   * get_request_metadata — captures the caller's IP + User-Agent
#   * require_audit_reader — gates the audit-log read endpoints to
#                            super-admins OR hospital admins
# ================================================================

import ipaddress
from typing import Annotated, Optional

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import UserRole
from app.database import get_db
from app.dependencies.auth import (
    get_current_membership,
    get_current_user,
    oauth2_scheme,
)
from app.models.user import User
from app.schemas.audit import AuditAccess, RequestMetadata
from app.utils.exceptions import ForbiddenError


# ----------------------------------------------------------------
# REQUEST METADATA
# ----------------------------------------------------------------

def _safe_ip(host: Optional[str]) -> Optional[str]:
    """
    Return host only if it parses as a real IP address. audit_logs.
    ip_address is the PostgreSQL INET type, which rejects non-IP
    strings — a test client's host ("testclient") or any other
    non-address value is stored as NULL rather than breaking the insert.
    """
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        return None


async def get_request_metadata(request: Request) -> RequestMetadata:
    """
    Capture the caller's network context for the audit trail. Both
    fields may be None — there is no client info, or the host is not a
    valid IP. Background / system actions never call this and pass a
    None request_meta to log_audit instead.
    """
    host = request.client.host if request.client else None
    return RequestMetadata(
        ip_address=_safe_ip(host),
        user_agent=request.headers.get("user-agent"),
    )


# ----------------------------------------------------------------
# READ GUARD — super-admin OR hospital-admin
# ----------------------------------------------------------------

async def require_audit_reader(
    current_user: Annotated[User, Depends(get_current_user)],
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditAccess:
    """
    Gate every audit-log read endpoint. Only two roles may query the
    audit trail:

      * super_admin    — sees every hospital's logs (cross-tenant).
        Does not need a hospital-scoped token.
      * hospital_admin — sees only their own hospital's logs.

    Any other role (doctor, nurse, receptionist, ...) raises
    ForbiddenError. Regular clinical staff must not see audit logs.
    """
    if current_user.system_role == UserRole.SUPER_ADMIN.value:
        return AuditAccess(is_super_admin=True, hospital_id=None)

    # Not a super-admin — require a hospital-scoped token whose role is
    # hospital_admin. get_current_membership re-validates the membership.
    membership = await get_current_membership(token, current_user, db)
    if membership.role.name != UserRole.HOSPITAL_ADMIN.value:
        raise ForbiddenError()
    return AuditAccess(is_super_admin=False, hospital_id=membership.hospital_id)

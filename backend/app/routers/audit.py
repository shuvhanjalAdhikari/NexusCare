# ================================================================
# NexusCare — app/routers/audit.py
# Read-only audit-log endpoints under /api/v1/audit-logs.
#
# There is NO write endpoint — audit rows are written internally by
# services via app.services.audit.log_audit(). Audit logs are
# append-only: no POST, no PATCH, no DELETE.
#
# Every endpoint is gated by require_audit_reader: only super-admins
# and hospital admins may query the audit trail. Super-admins see all
# hospitals; hospital admins see only their own (cross-tenant access
# surfaces as an empty list or NotFoundError, never ForbiddenError).
#
# Canonical naming: the path/query params are resource_type /
# resource_id — the real audit_logs column names. There are no
# entity_* columns.
# ================================================================

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.audit import require_audit_reader
from app.schemas.audit import AuditAccess, AuditLogListResponse, AuditLogResponse
from app.services import audit as audit_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit"])


# ----------------------------------------------------------------
# LIST — filtered + paginated
# ----------------------------------------------------------------

@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    access: Annotated[AuditAccess, Depends(require_audit_reader)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    action: Optional[str] = Query(
        default=None, description="Filter by action, e.g. 'login' or 'dispense'"
    ),
    resource_type: Optional[str] = Query(
        default=None,
        description="Filter by resource type, e.g. 'prescription_item'",
    ),
    user_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by the user who performed the action"
    ),
    hospital_id: Optional[uuid.UUID] = Query(
        default=None,
        description=(
            "Filter by hospital. Honoured for super-admins only; "
            "hospital admins are always pinned to their own hospital."
        ),
    ),
    from_date: Optional[date] = Query(
        default=None, description="Earliest created_at date (inclusive)"
    ),
    to_date: Optional[date] = Query(
        default=None, description="Latest created_at date (inclusive)"
    ),
):
    """Paginated audit-log list, newest first."""
    return await audit_service.list_audit_logs(
        db,
        access,
        pagination.page,
        pagination.size,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        hospital_id=hospital_id,
        from_date=from_date,
        to_date=to_date,
    )


# ----------------------------------------------------------------
# RESOURCE HISTORY — everything that happened to one resource
# ----------------------------------------------------------------

@router.get(
    "/entity/{resource_type}/{resource_id}",
    response_model=AuditLogListResponse,
)
async def get_resource_history(
    resource_type: str,
    resource_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    access: Annotated[AuditAccess, Depends(require_audit_reader)],
    pagination: Annotated[Pagination, Depends(Pagination)],
):
    """Full audit history of a single resource, newest first."""
    return await audit_service.list_resource_history(
        db, access, resource_type, resource_id, pagination.page, pagination.size
    )


# ----------------------------------------------------------------
# USER HISTORY — everything one user did
# ----------------------------------------------------------------

@router.get("/user/{user_id}", response_model=AuditLogListResponse)
async def get_user_history(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    access: Annotated[AuditAccess, Depends(require_audit_reader)],
    pagination: Annotated[Pagination, Depends(Pagination)],
):
    """Everything a specific user did, newest first."""
    return await audit_service.list_user_history(
        db, access, user_id, pagination.page, pagination.size
    )


# ----------------------------------------------------------------
# SINGLE ENTRY
# ----------------------------------------------------------------

@router.get("/{audit_log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    audit_log_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    access: Annotated[AuditAccess, Depends(require_audit_reader)],
):
    """Retrieve a single audit entry by id."""
    return await audit_service.get_audit_log(db, access, audit_log_id)

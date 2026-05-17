# ================================================================
# NexusCare — app/services/audit.py
# Audit-trail infrastructure: the log_audit() write helper plus the
# admin read queries.
#
# ----------------------------------------------------------------
# WHAT THIS MODULE IS
# ----------------------------------------------------------------
# An audit log is a permanent, APPEND-ONLY record of "user X did
# action Y to resource Z at time T". Rows are never updated and never
# deleted in v1 — once written, they are permanent.
#
# log_audit() is an INTERNAL helper. It is not exposed as an HTTP
# endpoint; there is no POST /audit-logs. Other services call it as
# part of their own logic.
#
# ----------------------------------------------------------------
# ATOMICITY
# ----------------------------------------------------------------
# log_audit() only calls db.add() — it never commits. The audit row
# rides on the CALLER'S open transaction and is committed (or rolled
# back) by the caller's own single commit. An audit entry can
# therefore never outlive a rolled-back action: a failed dispense
# leaves no dispense row AND no audit row.
#
# ----------------------------------------------------------------
# old_value / new_value CONVENTION
# ----------------------------------------------------------------
# old_value and new_value are the only structured JSONB fields on the
# table — there is no separate `changes` or `metadata` column.
#   * CREATE actions      — new_value only
#   * UPDATE actions      — old_value AND new_value
#   * DELETE/deactivate   — old_value (plus new_value for the new flag)
#   * LOGIN actions       — both may be null; the action is the data
# For non-before/after context (login-failure reasons, payment
# metadata, etc.), pack descriptive keys into new_value, e.g.
#   {"reason": "wrong_password"}
#   {"amount": "500", "method": "cash", "is_refund": False,
#    "payment_id": "..."}
#
# ----------------------------------------------------------------
# LOGIN EVENTS HAVE hospital_id = NULL
# ----------------------------------------------------------------
# login / login_failed / account_locked events occur BEFORE workspace
# selection, so hospital_id is NULL on those rows. Hospital admins
# scoped to a single hospital will NOT see login events in their audit
# views — this is by design. Only super-admins see login events. If
# hospitals need to audit user logins to their hospital specifically,
# a separate 'workspace_selected' audit event (TODO v2) would be the
# right place to capture it.
#
# ----------------------------------------------------------------
# WIRED AUDIT POINTS
# ----------------------------------------------------------------
# Phase 13:
#   login                  — services/auth.py:authenticate_user
#   login_failed           — services/auth.py:authenticate_user
#   account_locked         — services/auth.py:authenticate_user
#   dispense               — services/dispense.py:dispense_item
#   record_payment         — services/payment.py:record_payment
#   deactivate_membership  — services/user.py:soft_delete_membership
#   cancel_prescription    — services/prescription.py:update_prescription
# Phase 14:
#   delete_patient         — services/patient.py:soft_delete_patient
#   deactivate_doctor      — services/doctor.py:deactivate_doctor
#   cancel_invoice         — services/invoice.py:update_invoice
#   change_role            — services/user.py:update_membership
#   reset_password         — services/auth.py:reset_password
#
# TODO (v2 — retention): audit logs are NEVER deleted in v1. A future
# data-retention policy (e.g. purge rows older than 7 years for legal
# compliance) is the only sanctioned path to removing a row.
# ================================================================

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.schemas.audit import AuditAccess, RequestMetadata
from app.utils.exceptions import NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# JSONB SANITIZER
# ----------------------------------------------------------------

def _to_jsonable(value: Any) -> Any:
    """
    Recursively coerce a value into something the JSONB column can
    store. UUID / Decimal / datetime / date are stringified; any
    unrecognised type falls back to str(). This function never raises —
    it is the guarantee that a weird value in old_value / new_value
    cannot break the caller's commit.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return str(value)


# ----------------------------------------------------------------
# WRITE — the internal helper other services call
# ----------------------------------------------------------------

async def log_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    hospital_id: Optional[uuid.UUID] = None,
    membership_id: Optional[uuid.UUID] = None,
    old_value: Optional[dict[str, Any]] = None,
    new_value: Optional[dict[str, Any]] = None,
    request_meta: Optional[RequestMetadata] = None,
) -> Optional[AuditLog]:
    """
    Append one row to audit_logs inside the CALLER'S open transaction.

    The row is added with db.add() only — this function never commits.
    It is committed (or rolled back) by the caller's own single commit,
    which is what makes audit logging atomic with the action it records.

    Exception safety (best-effort, NOT gating)
    ------------------------------------------
    Audit logging must never break the action it records. Runtime data
    issues (an odd value that cannot be serialized, etc.) are caught,
    logged at WARNING, and swallowed — the caller's action still
    completes, just without an audit row. A dispense succeeding without
    its audit entry is preferable to a dispense failing because audit
    had a bug.

    Programmer errors are NOT swallowed: `action` and `resource_type`
    are required keyword arguments, so omitting them raises a TypeError
    before this body runs. That is a real bug and is surfaced in dev.

    old_value / new_value
    ---------------------
    See the module docstring for the convention. Both are passed through
    _to_jsonable() before insertion, so UUID / Decimal / datetime values
    are safe to include directly.
    """
    try:
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            hospital_id=hospital_id,
            membership_id=membership_id,
            old_value=_to_jsonable(old_value) if old_value is not None else None,
            new_value=_to_jsonable(new_value) if new_value is not None else None,
            ip_address=request_meta.ip_address if request_meta else None,
            user_agent=request_meta.user_agent if request_meta else None,
        )
        db.add(entry)
        return entry
    except Exception:
        # Best-effort: the caller's action must not fail because audit
        # logging hit a runtime data issue.
        logger.warning(
            "Audit log write failed; action proceeds without an audit row",
            exc_info=True,
            extra={
                "hospital_id": str(hospital_id) if hospital_id else None,
                "action": action,
            },
        )
        return None


# ----------------------------------------------------------------
# READ — admin queries
# ----------------------------------------------------------------

def _scope_conditions(access: AuditAccess) -> list:
    """
    Tenant scoping for every read query. A hospital admin is pinned to
    their own hospital_id; a super-admin gets no hospital filter and so
    sees every hospital's logs (including the hospital_id=NULL login
    events).
    """
    if access.is_super_admin:
        return []
    return [AuditLog.hospital_id == access.hospital_id]


async def list_audit_logs(
    db: AsyncSession,
    access: AuditAccess,
    page: int,
    size: int,
    *,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    hospital_id: Optional[uuid.UUID] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Paginated audit-log list, newest first.

    The hospital_id filter is honoured only for super-admins — a
    hospital admin is already pinned to their own hospital by
    _scope_conditions, so the parameter is ignored for them.
    """
    conditions = _scope_conditions(access)
    if access.is_super_admin and hospital_id is not None:
        conditions.append(AuditLog.hospital_id == hospital_id)
    if action is not None:
        conditions.append(AuditLog.action == action)
    if resource_type is not None:
        conditions.append(AuditLog.resource_type == resource_type)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if from_date is not None:
        conditions.append(AuditLog.created_at >= from_date)
    if to_date is not None:
        # to_date is inclusive of the whole day.
        conditions.append(AuditLog.created_at < to_date + timedelta(days=1))

    stmt = (
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


async def get_audit_log(
    db: AsyncSession, access: AuditAccess, audit_log_id: uuid.UUID
) -> AuditLog:
    """
    Return one audit entry. A hospital admin requesting an entry from
    another hospital gets NotFoundError, never ForbiddenError — the
    same cross-tenant rule as every data table (CLAUDE.md §13).
    """
    result = await db.execute(
        select(AuditLog).where(AuditLog.id == audit_log_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Audit log", audit_log_id)
    if not access.is_super_admin and entry.hospital_id != access.hospital_id:
        # Treat cross-tenant access as not found to avoid leaking existence.
        raise NotFoundError("Audit log", audit_log_id)
    return entry


async def list_resource_history(
    db: AsyncSession,
    access: AuditAccess,
    resource_type: str,
    resource_id: uuid.UUID,
    page: int,
    size: int,
) -> dict:
    """
    Full audit history of a single resource — everything that ever
    happened to one prescription, invoice, membership, etc. Scoped to
    the caller's hospital unless they are a super-admin.
    """
    conditions = _scope_conditions(access)
    conditions.append(AuditLog.resource_type == resource_type)
    conditions.append(AuditLog.resource_id == resource_id)
    stmt = (
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


async def list_user_history(
    db: AsyncSession,
    access: AuditAccess,
    target_user_id: uuid.UUID,
    page: int,
    size: int,
) -> dict:
    """
    Everything a specific user did. Scoped to the caller's hospital
    unless they are a super-admin.
    """
    conditions = _scope_conditions(access)
    conditions.append(AuditLog.user_id == target_user_id)
    stmt = (
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)

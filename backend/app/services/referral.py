# ================================================================
# NexusCare — app/services/referral.py
# Referral business logic + the referral state machine. All queries
# are hospital-scoped (CLAUDE.md §13).
#
# Authorization: v1 grants referral access to all hospital members.
# Role-based restrictions are a v2 enhancement.
#
# Referral state machine (PATCH /referrals transitions only):
#   pending  → accepted | rejected
#   accepted → completed
#   completed / rejected → terminal
#
# A referral is created during a visit; from_doctor_id is taken from
# that visit's doctor_id (never from the request body).
#
# referral_type:
#   * internal — to_doctor_id required, verified to belong to this
#     hospital (a doctor in another tenant surfaces as NotFoundError,
#     never ForbiddenError — existence is not leaked).
#   * external — external_hospital is a free-text outside facility.
# Schema-layer mutual exclusivity is enforced in schemas/referral.py.
# Inter-tenant referrals are deferred to v2.
#
# Orphan rule: a referral whose parent visit has been soft-deleted is
# functionally orphaned. list_referrals and get_referral both join the
# visit and require visits.deleted_at IS NULL, so an orphaned referral
# is excluded from the list and 404s on direct GET — consistent with
# soft-delete-everywhere behaviour.
# ================================================================

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import ReferralStatus, ReferralType
from app.models.doctor import Department, DoctorProfile
from app.models.visit import Referral, Visit
from app.schemas.referral import ReferralCreate, ReferralUpdate
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

_REFERRAL_TRANSITIONS: dict[str, set[str]] = {
    ReferralStatus.PENDING.value: {
        ReferralStatus.ACCEPTED.value,
        ReferralStatus.REJECTED.value,
    },
    ReferralStatus.ACCEPTED.value: {
        ReferralStatus.COMPLETED.value,
    },
    ReferralStatus.COMPLETED.value: set(),
    ReferralStatus.REJECTED.value: set(),
}


# ----------------------------------------------------------------
# INTERNAL LOADERS
# ----------------------------------------------------------------

async def _load_referral(
    db: AsyncSession, hospital_id: uuid.UUID, referral_id: uuid.UUID
) -> Referral:
    """
    Load a referral within the tenant whose parent visit is not
    soft-deleted. Cross-tenant, missing, or orphaned referrals surface
    as NotFoundError (CLAUDE.md §13).
    """
    result = await db.execute(
        select(Referral)
        .join(Visit, Referral.visit_id == Visit.id)
        .where(
            Referral.id == referral_id,
            Referral.hospital_id == hospital_id,
            Visit.deleted_at.is_(None),
        )
    )
    referral = result.scalar_one_or_none()
    if referral is None:
        raise NotFoundError("Referral", referral_id)
    return referral


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_referral(
    db: AsyncSession, hospital_id: uuid.UUID, referral_id: uuid.UUID
) -> Referral:
    """Return one referral. Orphaned referrals (parent visit deleted)
    surface as NotFoundError."""
    return await _load_referral(db, hospital_id, referral_id)


async def list_referrals(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    from_doctor_id: Optional[uuid.UUID] = None,
    to_doctor_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> dict:
    """
    Paginated referral list scoped to this hospital, ordered by
    created_at DESC. Referrals whose parent visit is soft-deleted are
    excluded.

    The frontend composes "incoming" / "outgoing" views by passing
    to_doctor_id / from_doctor_id; a directional filter is a v2
    enhancement.
    """
    conditions = [
        Referral.hospital_id == hospital_id,
        Visit.deleted_at.is_(None),
    ]
    if from_doctor_id is not None:
        conditions.append(Referral.from_doctor_id == from_doctor_id)
    if to_doctor_id is not None:
        conditions.append(Referral.to_doctor_id == to_doctor_id)
    if status is not None:
        conditions.append(Referral.status == status)
    if from_date is not None:
        conditions.append(Referral.created_at >= from_date)
    if to_date is not None:
        conditions.append(Referral.created_at <= to_date)

    stmt = (
        select(Referral)
        .join(Visit, Referral.visit_id == Visit.id)
        .where(*conditions)
        .order_by(Referral.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

async def create_referral(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: ReferralCreate,
) -> Referral:
    """
    Create a referral during a visit. from_doctor_id is taken from the
    visit's doctor. For an internal referral, to_doctor_id is verified
    to belong to this hospital; an optional to_department_id is
    likewise verified.
    """
    visit_result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.hospital_id == hospital_id,
            Visit.deleted_at.is_(None),
        )
    )
    visit = visit_result.scalar_one_or_none()
    if visit is None:
        raise NotFoundError("Visit", visit_id)

    if payload.referral_type == ReferralType.INTERNAL:
        doctor_result = await db.execute(
            select(DoctorProfile.id).where(
                DoctorProfile.id == payload.to_doctor_id,
                DoctorProfile.hospital_id == hospital_id,
            )
        )
        if doctor_result.first() is None:
            raise NotFoundError("Doctor", payload.to_doctor_id)

    if payload.to_department_id is not None:
        dept_result = await db.execute(
            select(Department.id).where(
                Department.id == payload.to_department_id,
                Department.hospital_id == hospital_id,
            )
        )
        if dept_result.first() is None:
            raise NotFoundError("Department", payload.to_department_id)

    referral = Referral(
        hospital_id=hospital_id,
        visit_id=visit_id,
        from_doctor_id=visit.doctor_id,
        to_doctor_id=payload.to_doctor_id,
        to_department_id=payload.to_department_id,
        referral_type=payload.referral_type.value,
        external_hospital=payload.external_hospital,
        reason=payload.reason,
        urgency=payload.urgency.value,
        status=ReferralStatus.PENDING.value,
        notes=payload.notes,
    )
    db.add(referral)
    await db.commit()
    await db.refresh(referral)
    logger.info(
        "Referral created",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "referral_id": str(referral.id),
        },
    )
    return referral


# ----------------------------------------------------------------
# UPDATE
# ----------------------------------------------------------------

async def update_referral(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    referral_id: uuid.UUID,
    payload: ReferralUpdate,
) -> Referral:
    """
    Partial update of a referral's status / urgency / notes. A status
    change is validated against the referral state machine.
    """
    referral = await _load_referral(db, hospital_id, referral_id)

    data = payload.model_dump(exclude_unset=True)
    new_status: Optional[ReferralStatus] = data.pop("status", None)

    if new_status is not None and new_status.value != referral.status:
        target = new_status.value
        allowed = _REFERRAL_TRANSITIONS.get(referral.status, set())
        if target not in allowed:
            logger.warning(
                "Rejected referral status transition",
                extra={
                    "hospital_id": str(hospital_id),
                    "referral_id": str(referral_id),
                },
            )
            raise BadRequestError(
                f"Cannot change referral status from "
                f"'{referral.status}' to '{target}'."
            )
        referral.status = target

    if "urgency" in data and data["urgency"] is not None:
        data["urgency"] = data["urgency"].value
    for field, value in data.items():
        setattr(referral, field, value)

    await db.commit()
    await db.refresh(referral)
    logger.info(
        "Referral updated",
        extra={
            "hospital_id": str(hospital_id),
            "referral_id": str(referral_id),
            "status": referral.status,
        },
    )
    return referral

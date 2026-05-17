# ================================================================
# NexusCare — app/services/followup.py
# Scheduled follow-up business logic. All queries are hospital-scoped
# (CLAUDE.md §13).
#
# A follow-up is created off a visit: patient_id and visit_id are
# taken from that visit, doctor_id defaults to the visit's doctor.
#
# Follow-up state machine (PATCH transitions only):
#   pending   → completed | cancelled | missed
#   completed → terminal
#   cancelled → terminal
#   missed    → terminal
# All three non-pending statuses are terminal. There is no automatic
# transition — "completed" never fires when a new visit is created.
#
# Cascade: a follow-up persists when its parent visit is soft-deleted.
# It is an independent scheduled event; list_followups still returns
# it. The visit_id remains as audit context even if GET /visits/{id}
# would 404.
#
# Follow-ups are hard-deleted (no deleted_at column) and carry no
# created_by columns — there is no audit wiring on this table.
# ================================================================

import logging
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import FollowupStatus
from app.models.doctor import DoctorProfile
from app.models.followup import Followup
from app.schemas.followup import FollowupCreate, FollowupUpdate
from app.services import visit as visit_service
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

_FOLLOWUP_TRANSITIONS: dict[str, set[str]] = {
    FollowupStatus.PENDING.value: {
        FollowupStatus.COMPLETED.value,
        FollowupStatus.CANCELLED.value,
        FollowupStatus.MISSED.value,
    },
    FollowupStatus.COMPLETED.value: set(),
    FollowupStatus.CANCELLED.value: set(),
    FollowupStatus.MISSED.value: set(),
}


async def _validate_doctor(
    db: AsyncSession, hospital_id: uuid.UUID, doctor_id: uuid.UUID
) -> None:
    """Confirm a doctor profile exists in this hospital."""
    result = await db.execute(
        select(DoctorProfile.id).where(
            DoctorProfile.id == doctor_id,
            DoctorProfile.hospital_id == hospital_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Doctor", doctor_id)


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

async def create_followup(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: FollowupCreate,
) -> Followup:
    """
    Schedule a follow-up off a visit. patient_id and visit_id come from
    the visit; doctor_id defaults to the visit's doctor when omitted.
    The follow-up opens in status 'pending'.
    """
    # get_visit is hospital-scoped and 404s on cross-tenant access.
    visit = await visit_service.get_visit(db, hospital_id, visit_id)

    doctor_id = visit.doctor_id
    if payload.doctor_id is not None and payload.doctor_id != visit.doctor_id:
        await _validate_doctor(db, hospital_id, payload.doctor_id)
        doctor_id = payload.doctor_id

    followup = Followup(
        hospital_id=hospital_id,
        patient_id=visit.patient_id,
        visit_id=visit.id,
        doctor_id=doctor_id,
        recommended_date=payload.recommended_date,
        notes=payload.notes,
        status=FollowupStatus.PENDING.value,
    )
    db.add(followup)
    await db.commit()
    await db.refresh(followup)
    logger.info(
        "Followup created",
        extra={
            "hospital_id": str(hospital_id),
            "followup_id": str(followup.id),
        },
    )
    return followup


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_followup(
    db: AsyncSession, hospital_id: uuid.UUID, followup_id: uuid.UUID
) -> Followup:
    """Return one follow-up. Cross-tenant access surfaces as NotFoundError."""
    result = await db.execute(
        select(Followup).where(
            Followup.id == followup_id,
            Followup.hospital_id == hospital_id,
        )
    )
    followup = result.scalar_one_or_none()
    if followup is None:
        raise NotFoundError("Followup", followup_id)
    return followup


async def list_followups(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    patient_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Paginated follow-up list scoped to this hospital, ordered by
    recommended_date ASC (soonest return first). from_date / to_date
    bound recommended_date inclusively.

    Follow-ups whose parent visit was soft-deleted are still returned.
    """
    conditions = [Followup.hospital_id == hospital_id]
    if patient_id is not None:
        conditions.append(Followup.patient_id == patient_id)
    if doctor_id is not None:
        conditions.append(Followup.doctor_id == doctor_id)
    if status is not None:
        conditions.append(Followup.status == status)
    if from_date is not None:
        conditions.append(Followup.recommended_date >= from_date)
    if to_date is not None:
        conditions.append(Followup.recommended_date <= to_date)

    stmt = (
        select(Followup)
        .where(*conditions)
        .order_by(Followup.recommended_date.asc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# UPDATE / DELETE
# ----------------------------------------------------------------

async def update_followup(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    followup_id: uuid.UUID,
    payload: FollowupUpdate,
) -> Followup:
    """
    Partial update. A status change is validated against the follow-up
    state machine; an illegal transition raises BadRequestError (400).
    recommended_date and notes can be edited at any time.
    """
    followup = await get_followup(db, hospital_id, followup_id)
    data = payload.model_dump(exclude_unset=True)

    new_status = data.pop("status", None)
    if new_status is not None:
        new_value = new_status.value if hasattr(new_status, "value") else new_status
        if new_value != followup.status:
            allowed = _FOLLOWUP_TRANSITIONS.get(followup.status, set())
            if new_value not in allowed:
                logger.warning(
                    "Rejected followup transition",
                    extra={
                        "hospital_id": str(hospital_id),
                        "followup_id": str(followup_id),
                    },
                )
                raise BadRequestError(
                    f"Cannot transition follow-up from '{followup.status}' "
                    f"to '{new_value}'."
                )
            followup.status = new_value

    for field, value in data.items():
        setattr(followup, field, value)

    await db.commit()
    await db.refresh(followup)
    logger.info(
        "Followup updated",
        extra={
            "hospital_id": str(hospital_id),
            "followup_id": str(followup_id),
        },
    )
    return followup


async def delete_followup(
    db: AsyncSession, hospital_id: uuid.UUID, followup_id: uuid.UUID
) -> None:
    """Hard delete — followups has no deleted_at column per 01_schema.sql."""
    followup = await get_followup(db, hospital_id, followup_id)
    await db.delete(followup)
    await db.commit()
    logger.info(
        "Followup deleted",
        extra={
            "hospital_id": str(hospital_id),
            "followup_id": str(followup_id),
        },
    )

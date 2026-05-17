# ================================================================
# NexusCare — app/services/feedback.py
# Patient satisfaction feedback business logic. All queries are
# hospital-scoped (CLAUDE.md §13).
#
# Feedback is an inbound, write-then-read record. v1 accepts it from
# any authenticated hospital member — staff enter it on the patient's
# behalf at the counter, a tablet, or via an SMS/QR gateway.
#
# Anonymity: True anonymous submission (no patient link at all) is
# deferred to v2 alongside the patient portal. v1 always stores
# patient_id (the DB column is NOT NULL); the is_anonymous flag
# controls whether the patient identity is displayed in admin views.
#
# Feedback is immutable — there is no update path. Corrections are
# made by deleting and re-creating. It is hard-deleted (no deleted_at)
# and carries only submitted_at (no created_at/updated_at).
# ================================================================

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import DoctorProfile
from app.models.followup import Feedback
from app.schemas.feedback import FeedbackCreate
from app.services import patient as patient_service
from app.utils.exceptions import NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

async def create_feedback(
    db: AsyncSession, hospital_id: uuid.UUID, payload: FeedbackCreate
) -> Feedback:
    """
    Record a feedback submission. patient_id is required and validated
    against this hospital; appointment_id and doctor_id are validated
    only when supplied.
    """
    # Confirms the patient exists in this hospital (404s otherwise).
    await patient_service.get_patient(db, hospital_id, payload.patient_id)

    if payload.appointment_id is not None:
        result = await db.execute(
            select(Appointment.id).where(
                Appointment.id == payload.appointment_id,
                Appointment.hospital_id == hospital_id,
                Appointment.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Appointment", payload.appointment_id)

    if payload.doctor_id is not None:
        result = await db.execute(
            select(DoctorProfile.id).where(
                DoctorProfile.id == payload.doctor_id,
                DoctorProfile.hospital_id == hospital_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Doctor", payload.doctor_id)

    feedback = Feedback(hospital_id=hospital_id, **payload.model_dump())
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    logger.info(
        "Feedback submitted",
        extra={
            "hospital_id": str(hospital_id),
            "feedback_id": str(feedback.id),
        },
    )
    return feedback


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_feedback(
    db: AsyncSession, hospital_id: uuid.UUID, feedback_id: uuid.UUID
) -> Feedback:
    """Return one feedback entry. Cross-tenant access surfaces as NotFoundError."""
    result = await db.execute(
        select(Feedback).where(
            Feedback.id == feedback_id,
            Feedback.hospital_id == hospital_id,
        )
    )
    feedback = result.scalar_one_or_none()
    if feedback is None:
        raise NotFoundError("Feedback", feedback_id)
    return feedback


async def list_feedback(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    doctor_id: Optional[uuid.UUID] = None,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> dict:
    """
    Paginated feedback list scoped to this hospital, newest first.
    The rating filters bound rating_overall; from_date / to_date bound
    submitted_at inclusively.
    """
    conditions = [Feedback.hospital_id == hospital_id]
    if doctor_id is not None:
        conditions.append(Feedback.doctor_id == doctor_id)
    if min_rating is not None:
        conditions.append(Feedback.rating_overall >= min_rating)
    if max_rating is not None:
        conditions.append(Feedback.rating_overall <= max_rating)
    if from_date is not None:
        conditions.append(Feedback.submitted_at >= from_date)
    if to_date is not None:
        conditions.append(Feedback.submitted_at <= to_date)

    stmt = (
        select(Feedback)
        .where(*conditions)
        .order_by(Feedback.submitted_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# DELETE
# ----------------------------------------------------------------

async def delete_feedback(
    db: AsyncSession, hospital_id: uuid.UUID, feedback_id: uuid.UUID
) -> None:
    """Hard delete — feedback has no deleted_at column. Rare; admin-only."""
    feedback = await get_feedback(db, hospital_id, feedback_id)
    await db.delete(feedback)
    await db.commit()
    logger.info(
        "Feedback deleted",
        extra={
            "hospital_id": str(hospital_id),
            "feedback_id": str(feedback_id),
        },
    )

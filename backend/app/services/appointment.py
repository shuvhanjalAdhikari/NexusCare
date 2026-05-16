# ================================================================
# NexusCare — app/services/appointment.py
# Appointment CRUD, the appointment state machine, slot-availability
# validation for booking, and the cancel → queue cascade.
# All queries are hospital-scoped (CLAUDE.md §13).
#
# State machine (PATCH /appointments transitions only):
#   scheduled  → confirmed | cancelled | no_show
#   confirmed  → cancelled | no_show
#   checked_in → cancelled
#   completed / cancelled / no_show → terminal
# checked_in, in_consultation and completed are NEVER set through
# PATCH — they are driven by the OPD queue (POST /queue check-in and
# PATCH /queue status sync). A PATCH attempting them raises 400.
#
# Booking validation (create + reschedule) is a 3-stage check, each
# stage with a distinct error so the client can react precisely:
#   1. approved leave covers the date       → DoctorOnLeaveError (409)
#   2. time falls outside a working window  → BadRequestError   (400)
#   3. interval overlaps another booking    → SlotUnavailableError (409)
#
# Tenant note: appointments.patient_id / doctor_id carry no FK or
# CHECK enforcing hospital equality, so create_appointment loads both
# parents hospital-scoped before inserting.
# ================================================================

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import AppointmentStatus, AppointmentType, QueueStatus
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate
from app.services import slot as slot_service
from app.utils.exceptions import (
    BadRequestError,
    DoctorOnLeaveError,
    NotFoundError,
    SlotUnavailableError,
)
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

# Transitions a client may request via PATCH /appointments. The
# queue-driven targets (checked_in, in_consultation, completed) are
# deliberately absent — see the module docstring.
_PATCH_TRANSITIONS: dict[str, set[str]] = {
    AppointmentStatus.SCHEDULED.value: {
        AppointmentStatus.CONFIRMED.value,
        AppointmentStatus.CANCELLED.value,
        AppointmentStatus.NO_SHOW.value,
    },
    AppointmentStatus.CONFIRMED.value: {
        AppointmentStatus.CANCELLED.value,
        AppointmentStatus.NO_SHOW.value,
    },
    AppointmentStatus.CHECKED_IN.value: {
        AppointmentStatus.CANCELLED.value,
    },
    AppointmentStatus.IN_CONSULTATION.value: set(),
    AppointmentStatus.COMPLETED.value: set(),
    AppointmentStatus.CANCELLED.value: set(),
    AppointmentStatus.NO_SHOW.value: set(),
}

# Statuses from which a cancel (PATCH status=cancelled or DELETE) is
# permitted. in_consultation/completed/terminal cancels are rejected.
_CANCELLABLE_STATUSES = frozenset({
    AppointmentStatus.SCHEDULED.value,
    AppointmentStatus.CONFIRMED.value,
    AppointmentStatus.CHECKED_IN.value,
})

# Statuses a PATCH may never set directly — the queue owns these.
_QUEUE_DRIVEN_STATUSES = frozenset({
    AppointmentStatus.CHECKED_IN.value,
    AppointmentStatus.IN_CONSULTATION.value,
    AppointmentStatus.COMPLETED.value,
})


# ----------------------------------------------------------------
# INTERNAL LOADERS
# ----------------------------------------------------------------

async def _load_appointment(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    with_detail: bool = False,
    with_queue: bool = False,
) -> Appointment:
    """
    Load a non-deleted appointment within the tenant. Cross-tenant or
    missing rows surface as NotFoundError (CLAUDE.md §13).

    with_detail eager-loads patient + doctor.user for detail responses;
    with_queue eager-loads the linked queue entry for the cancel cascade.
    """
    options = []
    if with_detail:
        options.append(selectinload(Appointment.patient))
        options.append(
            selectinload(Appointment.doctor).selectinload(
                __import__("app.models.doctor", fromlist=["DoctorProfile"]).DoctorProfile.user
            )
        )
    if with_queue:
        options.append(selectinload(Appointment.queue_entry))

    stmt = select(Appointment).where(
        Appointment.id == appointment_id,
        Appointment.hospital_id == hospital_id,
        Appointment.deleted_at.is_(None),
    )
    if options:
        stmt = stmt.options(*options)

    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise NotFoundError("Appointment", appointment_id)
    return appointment


def _detail_dict(appointment: Appointment) -> dict:
    """Flatten an appointment + its eagerly-loaded patient/doctor into
    the shape AppointmentDetailResponse expects."""
    return {
        "id": appointment.id,
        "hospital_id": appointment.hospital_id,
        "patient_id": appointment.patient_id,
        "doctor_id": appointment.doctor_id,
        "department_id": appointment.department_id,
        "appointment_type": appointment.appointment_type,
        "scheduled_at": appointment.scheduled_at,
        "duration_minutes": appointment.duration_minutes,
        "status": appointment.status,
        "notes": appointment.notes,
        "booked_by": appointment.booked_by,
        "booked_by_membership_id": appointment.booked_by_membership_id,
        "created_at": appointment.created_at,
        "updated_at": appointment.updated_at,
        "patient": appointment.patient,
        "doctor": {
            "id": appointment.doctor.id,
            "first_name": appointment.doctor.user.first_name,
            "last_name": appointment.doctor.user.last_name,
            "specialization": appointment.doctor.specialization,
        },
    }


# ----------------------------------------------------------------
# BOOKING VALIDATION
# ----------------------------------------------------------------

def _localize(scheduled_at: datetime, tz) -> datetime:
    """Attach the hospital timezone to a naive scheduled_at; pass an
    already-aware value through unchanged."""
    if scheduled_at.tzinfo is None:
        return scheduled_at.replace(tzinfo=tz)
    return scheduled_at


async def _resolve_duration(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    target_date: date,
    start_local: datetime,
    explicit: Optional[int],
) -> int:
    """Pick the appointment duration: the explicit payload value, else
    the slot length of the working window containing the start time,
    else the module default."""
    if explicit is not None:
        return explicit
    windows = await slot_service.get_day_windows(db, hospital_id, doctor_id, target_date)
    start_t = start_local.time()
    for w_start, w_end, w_duration in windows:
        if w_start <= start_t < w_end:
            return w_duration
    return slot_service.DEFAULT_SLOT_DURATION_MINUTES


async def _validate_booking(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    start_local: datetime,
    duration_minutes: int,
    tz,
    *,
    exclude_appointment_id: Optional[uuid.UUID] = None,
) -> None:
    """Run the 3-stage booking check. Raises on the first failure."""
    target_date = start_local.date()

    if await slot_service.is_doctor_on_leave(db, hospital_id, doctor_id, target_date):
        logger.warning(
            "Booking rejected — doctor on leave",
            extra={"hospital_id": str(hospital_id), "doctor_id": str(doctor_id)},
        )
        raise DoctorOnLeaveError()

    windows = await slot_service.get_day_windows(db, hospital_id, doctor_id, target_date)
    if not windows:
        raise BadRequestError("The doctor is not available on this date.")

    end_local = start_local + timedelta(minutes=duration_minutes)
    if end_local.date() != start_local.date():
        raise BadRequestError("An appointment cannot extend past midnight.")

    start_t, end_t = start_local.time(), end_local.time()
    within_hours = any(
        w_start <= start_t and end_t <= w_end for w_start, w_end, _ in windows
    )
    if not within_hours:
        raise BadRequestError(
            "The requested time is outside the doctor's working hours for this date."
        )

    booked = await slot_service.get_booked_intervals(
        db, hospital_id, doctor_id, target_date, tz,
        exclude_appointment_id=exclude_appointment_id,
    )
    if any(b_start < end_local and b_end > start_local for b_start, b_end in booked):
        logger.warning(
            "Booking rejected — slot overlap",
            extra={"hospital_id": str(hospital_id), "doctor_id": str(doctor_id)},
        )
        raise SlotUnavailableError()


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_appointment_detail(
    db: AsyncSession, hospital_id: uuid.UUID, appointment_id: uuid.UUID
) -> dict:
    """Return one appointment with embedded patient + doctor identity."""
    appointment = await _load_appointment(
        db, hospital_id, appointment_id, with_detail=True
    )
    return _detail_dict(appointment)


async def list_appointments(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> dict:
    """
    Paginated appointment list scoped to this hospital.

    from_date / to_date bound scheduled_at (inclusive lower, exclusive
    upper is the caller's responsibility). Ordered by scheduled_at ASC
    so an upcoming-appointments view reads naturally.
    """
    conditions = [
        Appointment.hospital_id == hospital_id,
        Appointment.deleted_at.is_(None),
    ]
    if doctor_id is not None:
        conditions.append(Appointment.doctor_id == doctor_id)
    if patient_id is not None:
        conditions.append(Appointment.patient_id == patient_id)
    if status is not None:
        conditions.append(Appointment.status == status)
    if from_date is not None:
        conditions.append(Appointment.scheduled_at >= from_date)
    if to_date is not None:
        conditions.append(Appointment.scheduled_at <= to_date)

    stmt = (
        select(Appointment)
        .where(*conditions)
        .order_by(Appointment.scheduled_at.asc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

async def create_appointment(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    payload: AppointmentCreate,
    *,
    booked_by: uuid.UUID,
    booked_by_membership_id: uuid.UUID,
    tz_name: str,
) -> Appointment:
    """
    Book a new appointment after running the 3-stage availability check.

    appointment_type='walkin' is rejected here — walk-ins enter the OPD
    queue directly via POST /api/v1/queue and never create an
    appointment row.
    """
    if payload.appointment_type == AppointmentType.WALKIN:
        raise BadRequestError(
            "Walk-ins are created via POST /queue, not /appointments."
        )

    # Tenant ownership of patient + doctor (no FK enforces hospital equality).
    patient_result = await db.execute(
        select(Patient.id).where(
            Patient.id == payload.patient_id,
            Patient.hospital_id == hospital_id,
            Patient.deleted_at.is_(None),
        )
    )
    if patient_result.first() is None:
        raise NotFoundError("Patient", payload.patient_id)
    await slot_service.load_doctor_scoped(db, hospital_id, payload.doctor_id)

    tz = slot_service.resolve_tz(tz_name)
    start_local = _localize(payload.scheduled_at, tz).astimezone(tz)
    target_date = start_local.date()

    duration = await _resolve_duration(
        db, hospital_id, payload.doctor_id, target_date, start_local,
        payload.duration_minutes,
    )
    await _validate_booking(
        db, hospital_id, payload.doctor_id, start_local, duration, tz,
    )

    appointment = Appointment(
        hospital_id=hospital_id,
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        department_id=payload.department_id,
        appointment_type=payload.appointment_type.value,
        scheduled_at=start_local,
        duration_minutes=duration,
        status=AppointmentStatus.SCHEDULED.value,
        notes=payload.notes,
        booked_by=booked_by,
        booked_by_membership_id=booked_by_membership_id,
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    logger.info(
        "Appointment created",
        extra={
            "hospital_id": str(hospital_id),
            "appointment_id": str(appointment.id),
            "doctor_id": str(payload.doctor_id),
        },
    )
    return appointment


# ----------------------------------------------------------------
# UPDATE
# ----------------------------------------------------------------

async def update_appointment(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    *,
    tz_name: str,
) -> Appointment:
    """
    Partial update of status / scheduled_at / duration / department /
    notes.

    A status=cancelled request is routed through cancel_appointment so
    the queue cascade runs. Any other status change is checked against
    the PATCH transition table. Rescheduling (scheduled_at change)
    re-runs the full booking validation, excluding this appointment
    from the overlap check.
    """
    appointment = await _load_appointment(db, hospital_id, appointment_id)

    data = payload.model_dump(exclude_unset=True)
    new_status: Optional[AppointmentStatus] = data.pop("status", None)

    if new_status is not None:
        target = new_status.value
        if target == AppointmentStatus.CANCELLED.value:
            # cancel_appointment soft-deletes the row, so it must own the
            # response — re-loading here would hit the deleted_at filter.
            return await cancel_appointment(db, hospital_id, appointment_id)
        if target in _QUEUE_DRIVEN_STATUSES:
            raise BadRequestError(
                f"Status '{target}' is set automatically by the OPD queue, "
                "not via PATCH."
            )
        if target != appointment.status:
            allowed = _PATCH_TRANSITIONS.get(appointment.status, set())
            if target not in allowed:
                raise BadRequestError(
                    f"Cannot change appointment status from "
                    f"'{appointment.status}' to '{target}'."
                )

    # Reschedule re-validation — uses the merged scheduled_at/duration.
    reschedule = "scheduled_at" in data or "duration_minutes" in data
    if reschedule:
        tz = slot_service.resolve_tz(tz_name)
        new_dt = data.get("scheduled_at", appointment.scheduled_at)
        start_local = _localize(new_dt, tz).astimezone(tz)
        duration = data.get("duration_minutes", appointment.duration_minutes)
        await _validate_booking(
            db, hospital_id, appointment.doctor_id, start_local, duration, tz,
            exclude_appointment_id=appointment.id,
        )
        data["scheduled_at"] = start_local
        data["duration_minutes"] = duration

    for field, value in data.items():
        setattr(appointment, field, value)
    if new_status is not None and new_status.value != appointment.status:
        appointment.status = new_status.value

    await db.commit()
    await db.refresh(appointment)
    logger.info(
        "Appointment updated",
        extra={
            "hospital_id": str(hospital_id),
            "appointment_id": str(appointment_id),
            "status": appointment.status,
        },
    )
    return appointment


# ----------------------------------------------------------------
# CANCEL (+ queue cascade)
# ----------------------------------------------------------------

async def cancel_appointment(
    db: AsyncSession, hospital_id: uuid.UUID, appointment_id: uuid.UUID
) -> Appointment:
    """
    Cancel an appointment: set status='cancelled', stamp deleted_at,
    and cascade to its OPD queue entry.

    Cascade rules:
      * queue entry in_consultation → reject the whole cancel: the
        visit has already started (BadRequestError).
      * queue entry waiting/called  → set it to 'skipped'. called_at
        and counter_no are KEPT — they are audit fields recording what
        happened, not live state.
      * no queue entry              → cancel the appointment only.

    Accepted v1 race: between reading queue.status here and writing
    'skipped', a parallel PATCH /queue could move the entry to
    in_consultation. The window is small and the only consequence is a
    stale skip (not corruption). Hardening would take SELECT FOR UPDATE
    on the queue row, or an advisory lock keyed on appointment_id.
    """
    appointment = await _load_appointment(
        db, hospital_id, appointment_id, with_queue=True
    )

    if appointment.status not in _CANCELLABLE_STATUSES:
        raise BadRequestError(
            f"An appointment with status '{appointment.status}' cannot be cancelled."
        )

    queue_entry = appointment.queue_entry
    if queue_entry is not None:
        if queue_entry.status == QueueStatus.IN_CONSULTATION.value:
            raise BadRequestError(
                "Cannot cancel an appointment whose visit is already in progress."
            )
        if queue_entry.status in (
            QueueStatus.WAITING.value,
            QueueStatus.CALLED.value,
        ):
            # Keep called_at / counter_no — audit, not current state.
            queue_entry.status = QueueStatus.SKIPPED.value

    appointment.status = AppointmentStatus.CANCELLED.value
    appointment.deleted_at = datetime.now(timezone.utc)

    await db.commit()
    # Refresh by primary key (no deleted_at filter) so the now
    # soft-deleted row can still be serialized into the response.
    await db.refresh(appointment)
    logger.info(
        "Appointment cancelled",
        extra={
            "hospital_id": str(hospital_id),
            "appointment_id": str(appointment_id),
            "queue_cascaded": queue_entry is not None,
        },
    )
    return appointment

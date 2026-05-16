# ================================================================
# NexusCare — app/services/queue.py
# OPD queue business logic: walk-in registration, appointment
# check-in, the queue state machine, "call next", and daily stats.
# All queries are hospital-scoped (CLAUDE.md §13).
#
# "Today" — opd_queue has no date column, so a day is derived from
# created_at (TIMESTAMPTZ) bounded by the hospital's local midnight.
# queue_number is sequential per (doctor, local day).
#
# queue_number assignment is serialized with a transaction-scoped
# Postgres advisory lock. opd_queue has no UNIQUE constraint on
# (doctor, queue_number, day), so the insert cannot be retried on a
# violation — the lock prevents the collision instead. The lock key is
#     f"queue:{doctor_id}:{local_date.isoformat()}"
# hashed by Postgres' hashtext() (stable across backends, unlike
# Python's salted hash()), then passed to pg_advisory_xact_lock, which
# releases automatically on commit or rollback.
#
# The 'skipped' queue status carries TWO meanings — both mean the
# patient left the active flow without a consultation:
#   1. An admin manually skipped a waiting/called patient (e.g. the
#      patient stepped out).
#   2. The linked appointment was cancelled while the queue entry was
#      still waiting/called (cascade from appointment cancellation).
# ================================================================

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import AppointmentStatus, QueueStatus
from app.models.appointment import Appointment, OPDQueue
from app.models.patient import Patient
from app.schemas.queue import QueueAddRequest, QueueUpdate
from app.services import slot as slot_service
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

# Valid queue status transitions. waiting may jump straight to
# in_consultation (the "called" step is optional for walk-ins and
# fast-moving OPDs). completed and skipped are terminal.
_QUEUE_TRANSITIONS: dict[str, set[str]] = {
    QueueStatus.WAITING.value: {
        QueueStatus.CALLED.value,
        QueueStatus.IN_CONSULTATION.value,
        QueueStatus.SKIPPED.value,
    },
    QueueStatus.CALLED.value: {
        QueueStatus.IN_CONSULTATION.value,
        QueueStatus.SKIPPED.value,
    },
    QueueStatus.IN_CONSULTATION.value: {
        QueueStatus.COMPLETED.value,
    },
    QueueStatus.COMPLETED.value: set(),
    QueueStatus.SKIPPED.value: set(),
}

# Appointment statuses from which a check-in is allowed.
_CHECKINABLE_STATUSES = frozenset({
    AppointmentStatus.SCHEDULED.value,
    AppointmentStatus.CONFIRMED.value,
})


# ----------------------------------------------------------------
# RESPONSE ASSEMBLY
# ----------------------------------------------------------------

def _entry_dict(entry: OPDQueue, patient: Patient) -> dict:
    """Flatten a queue entry + its patient into the QueueResponse shape.
    opd_queue has no `patient` relationship, so the patient is loaded
    explicitly and passed in."""
    return {
        "id": entry.id,
        "hospital_id": entry.hospital_id,
        "appointment_id": entry.appointment_id,
        "patient_id": entry.patient_id,
        "doctor_id": entry.doctor_id,
        "queue_number": entry.queue_number,
        "priority": entry.priority,
        "status": entry.status,
        "counter_no": entry.counter_no,
        "estimated_wait_minutes": entry.estimated_wait_minutes,
        "checked_in_at": entry.checked_in_at,
        "called_at": entry.called_at,
        "completed_at": entry.completed_at,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "patient": patient,
    }


async def _load_entry(
    db: AsyncSession, hospital_id: uuid.UUID, queue_id: uuid.UUID
) -> OPDQueue:
    """Load a queue entry within the tenant. Cross-tenant or missing
    rows surface as NotFoundError (CLAUDE.md §13)."""
    result = await db.execute(
        select(OPDQueue).where(
            OPDQueue.id == queue_id,
            OPDQueue.hospital_id == hospital_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Queue entry", queue_id)
    return entry


# ----------------------------------------------------------------
# ADD TO QUEUE — walk-in OR check-in
# ----------------------------------------------------------------

async def add_to_queue(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    payload: QueueAddRequest,
    *,
    current_user_id: uuid.UUID,
    membership_id: uuid.UUID,
    tz_name: str,
) -> dict:
    """
    Add a patient to a doctor's OPD queue.

    Two modes (the request schema guarantees exactly one applies):
      * Check-in — payload.appointment_id set. The appointment must be
        scheduled or confirmed; it is flipped to 'checked_in' in the
        same commit. patient/doctor are taken from the appointment.
      * Walk-in  — payload.patient_id + doctor_id set, no appointment.

    queue_number is the next integer for the doctor on the hospital's
    local day, assigned under an advisory lock (see module docstring).
    """
    tz = slot_service.resolve_tz(tz_name)
    local_date = datetime.now(tz).date()

    appointment: Optional[Appointment] = None
    if payload.appointment_id is not None:
        appointment = await _load_checkin_appointment(
            db, hospital_id, payload.appointment_id
        )
        patient_id = appointment.patient_id
        doctor_id = appointment.doctor_id
    else:
        patient_id = payload.patient_id
        doctor_id = payload.doctor_id
        await _verify_patient(db, hospital_id, patient_id)
        await slot_service.load_doctor_scoped(db, hospital_id, doctor_id)

    queue_number = await _next_queue_number(
        db, hospital_id, doctor_id, local_date, tz
    )

    entry = OPDQueue(
        hospital_id=hospital_id,
        appointment_id=payload.appointment_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        queue_number=queue_number,
        priority=payload.priority.value,
        status=QueueStatus.WAITING.value,
        counter_no=payload.counter_no,
        checked_in_at=datetime.now(timezone.utc),
    )
    db.add(entry)

    if appointment is not None:
        appointment.status = AppointmentStatus.CHECKED_IN.value

    await db.commit()
    await db.refresh(entry)

    patient = await db.get(Patient, patient_id)
    logger.info(
        "Queue entry created",
        extra={
            "hospital_id": str(hospital_id),
            "queue_id": str(entry.id),
            "doctor_id": str(doctor_id),
            "queue_number": queue_number,
            "mode": "check_in" if appointment is not None else "walk_in",
            "user_id": str(current_user_id),
            "membership_id": str(membership_id),
        },
    )
    return _entry_dict(entry, patient)


async def _load_checkin_appointment(
    db: AsyncSession, hospital_id: uuid.UUID, appointment_id: uuid.UUID
) -> Appointment:
    """Load + validate an appointment for check-in."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.hospital_id == hospital_id,
            Appointment.deleted_at.is_(None),
        )
    )
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise NotFoundError("Appointment", appointment_id)
    if appointment.status not in _CHECKINABLE_STATUSES:
        raise BadRequestError(
            "Only a scheduled or confirmed appointment can be checked in "
            f"(current status: '{appointment.status}')."
        )
    return appointment


async def _verify_patient(
    db: AsyncSession, hospital_id: uuid.UUID, patient_id: uuid.UUID
) -> None:
    """Confirm a walk-in patient belongs to this hospital and is not
    soft-deleted."""
    result = await db.execute(
        select(Patient.id).where(
            Patient.id == patient_id,
            Patient.hospital_id == hospital_id,
            Patient.deleted_at.is_(None),
        )
    )
    if result.first() is None:
        raise NotFoundError("Patient", patient_id)


async def _next_queue_number(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    local_date: date,
    tz,
) -> int:
    """
    Return the next queue_number for a doctor on local_date.

    A transaction-scoped advisory lock keyed on
    f"queue:{doctor_id}:{local_date.isoformat()}" serializes concurrent
    callers so two entries can never receive the same number. The lock
    is held until the surrounding transaction commits in add_to_queue.
    """
    lock_key = f"queue:{doctor_id}:{local_date.isoformat()}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": lock_key},
    )

    day_start_utc, day_end_utc = slot_service.local_day_bounds_utc(local_date, tz)
    result = await db.execute(
        select(func.coalesce(func.max(OPDQueue.queue_number), 0)).where(
            OPDQueue.hospital_id == hospital_id,
            OPDQueue.doctor_id == doctor_id,
            OPDQueue.created_at >= day_start_utc,
            OPDQueue.created_at < day_end_utc,
        )
    )
    return int(result.scalar_one()) + 1


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def list_queue(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    tz_name: str,
    *,
    doctor_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> list[dict]:
    """
    Return today's queue (hospital local day), ordered by queue_number.
    Optionally filtered by doctor and/or status.
    """
    tz = slot_service.resolve_tz(tz_name)
    local_date = datetime.now(tz).date()
    day_start_utc, day_end_utc = slot_service.local_day_bounds_utc(local_date, tz)

    conditions = [
        OPDQueue.hospital_id == hospital_id,
        OPDQueue.created_at >= day_start_utc,
        OPDQueue.created_at < day_end_utc,
    ]
    if doctor_id is not None:
        conditions.append(OPDQueue.doctor_id == doctor_id)
    if status is not None:
        conditions.append(OPDQueue.status == status)

    result = await db.execute(
        select(OPDQueue, Patient)
        .join(Patient, OPDQueue.patient_id == Patient.id)
        .where(*conditions)
        .order_by(OPDQueue.queue_number.asc())
    )
    return [_entry_dict(entry, patient) for entry, patient in result.all()]


async def get_next_waiting(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    tz_name: str,
) -> Optional[dict]:
    """
    Return the doctor's next waiting patient — the lowest queue_number
    with status='waiting' on the hospital's local day — or None if the
    waiting queue is empty.
    """
    tz = slot_service.resolve_tz(tz_name)
    local_date = datetime.now(tz).date()
    day_start_utc, day_end_utc = slot_service.local_day_bounds_utc(local_date, tz)

    result = await db.execute(
        select(OPDQueue, Patient)
        .join(Patient, OPDQueue.patient_id == Patient.id)
        .where(
            OPDQueue.hospital_id == hospital_id,
            OPDQueue.doctor_id == doctor_id,
            OPDQueue.status == QueueStatus.WAITING.value,
            OPDQueue.created_at >= day_start_utc,
            OPDQueue.created_at < day_end_utc,
        )
        .order_by(OPDQueue.queue_number.asc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    entry, patient = row
    return _entry_dict(entry, patient)


# ----------------------------------------------------------------
# UPDATE — queue state machine
# ----------------------------------------------------------------

async def update_queue_entry(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    queue_id: uuid.UUID,
    payload: QueueUpdate,
    *,
    current_user_id: uuid.UUID,
    membership_id: uuid.UUID,
) -> dict:
    """
    Update a queue entry's status / counter_no / estimated wait.

    Status transitions follow the queue state machine. Side effects:
      * → called          : stamp called_at (first time only)
      * → in_consultation : sync the linked appointment to in_consultation
      * → completed       : stamp completed_at, sync appointment to completed
    A linked appointment is only synced when one exists (walk-ins have
    none).
    """
    entry = await _load_entry(db, hospital_id, queue_id)

    data = payload.model_dump(exclude_unset=True)
    new_status: Optional[QueueStatus] = data.pop("status", None)

    for field, value in data.items():
        setattr(entry, field, value)

    if new_status is not None and new_status.value != entry.status:
        target = new_status.value
        allowed = _QUEUE_TRANSITIONS.get(entry.status, set())
        if target not in allowed:
            raise BadRequestError(
                f"Cannot change queue status from '{entry.status}' to '{target}'."
            )

        now = datetime.now(timezone.utc)
        if target == QueueStatus.CALLED.value and entry.called_at is None:
            entry.called_at = now
        elif target == QueueStatus.IN_CONSULTATION.value:
            await _sync_appointment(db, entry, AppointmentStatus.IN_CONSULTATION.value)
        elif target == QueueStatus.COMPLETED.value:
            entry.completed_at = now
            await _sync_appointment(db, entry, AppointmentStatus.COMPLETED.value)

        entry.status = target

    await db.commit()
    await db.refresh(entry)

    patient = await db.get(Patient, entry.patient_id)
    logger.info(
        "Queue entry updated",
        extra={
            "hospital_id": str(hospital_id),
            "queue_id": str(queue_id),
            "status": entry.status,
            "user_id": str(current_user_id),
            "membership_id": str(membership_id),
        },
    )
    return _entry_dict(entry, patient)


async def _sync_appointment(
    db: AsyncSession, entry: OPDQueue, new_status: str
) -> None:
    """Mirror a queue status change onto the linked appointment, if any.
    Walk-in entries have no appointment_id and are skipped."""
    if entry.appointment_id is None:
        return
    appointment = await db.get(Appointment, entry.appointment_id)
    if appointment is not None:
        appointment.status = new_status


# ----------------------------------------------------------------
# DAILY STATS
# ----------------------------------------------------------------

async def get_today_stats(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    tz_name: str,
) -> dict:
    """
    Return per-doctor counts for the hospital's current local day.

    Mixed source by design: every count derives from opd_queue EXCEPT
    no_show, which has no queue status and is counted from appointments
    (scheduled_at on the local day, status='no_show'). The queue tracks
    live flow; no_show is reconciled from unattended appointments.
    """
    await slot_service.load_doctor_scoped(db, hospital_id, doctor_id)

    tz = slot_service.resolve_tz(tz_name)
    local_date = datetime.now(tz).date()
    day_start_utc, day_end_utc = slot_service.local_day_bounds_utc(local_date, tz)

    # Queue counts grouped by status.
    status_result = await db.execute(
        select(OPDQueue.status, func.count(OPDQueue.id))
        .where(
            OPDQueue.hospital_id == hospital_id,
            OPDQueue.doctor_id == doctor_id,
            OPDQueue.created_at >= day_start_utc,
            OPDQueue.created_at < day_end_utc,
        )
        .group_by(OPDQueue.status)
    )
    counts = {row[0]: row[1] for row in status_result.all()}

    # Walk-ins: queue entries with no linked appointment.
    walkin_result = await db.execute(
        select(func.count(OPDQueue.id)).where(
            OPDQueue.hospital_id == hospital_id,
            OPDQueue.doctor_id == doctor_id,
            OPDQueue.appointment_id.is_(None),
            OPDQueue.created_at >= day_start_utc,
            OPDQueue.created_at < day_end_utc,
        )
    )
    walk_ins = int(walkin_result.scalar_one())

    # no_show comes from appointments, not the queue.
    no_show_result = await db.execute(
        select(func.count(Appointment.id)).where(
            Appointment.hospital_id == hospital_id,
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.NO_SHOW.value,
            Appointment.scheduled_at >= day_start_utc,
            Appointment.scheduled_at < day_end_utc,
        )
    )
    no_show = int(no_show_result.scalar_one())

    waiting = counts.get(QueueStatus.WAITING.value, 0)
    called = counts.get(QueueStatus.CALLED.value, 0)
    in_consultation = counts.get(QueueStatus.IN_CONSULTATION.value, 0)
    completed = counts.get(QueueStatus.COMPLETED.value, 0)
    skipped = counts.get(QueueStatus.SKIPPED.value, 0)

    return {
        "doctor_id": doctor_id,
        "date": local_date,
        "total_in_queue": waiting + called + in_consultation + completed + skipped,
        "waiting": waiting,
        "called": called,
        "in_consultation": in_consultation,
        "completed": completed,
        "skipped": skipped,
        "walk_ins": walk_ins,
        "no_show": no_show,
    }

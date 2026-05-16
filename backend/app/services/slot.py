# ================================================================
# NexusCare — app/services/slot.py
# Available-slot computation for doctor appointment booking.
#
# This is the most timing-sensitive code in the appointment module.
# Everything here is anchored to the HOSPITAL's local timezone, not
# UTC or the server clock:
#   * A doctor_schedule row stores a naive weekday + TIME (local).
#   * A doctor_schedule_override stores a naive local date + TIME.
#   * An appointment stores scheduled_at as TIMESTAMPTZ (an absolute
#     instant).
# To decide whether a slot is free we convert booked appointments
# back into the hospital's local wall-clock and compare there.
#
# day_of_week mapping: the schema stores 0=Sunday .. 6=Saturday.
# Python's date.weekday() returns 0=Monday .. 6=Sunday, so the
# conversion is (weekday() + 1) % 7.
#
# Precedence rules (applied in compute_available_slots):
#   1. An approved leave covering the date  → no slots.
#   2. A schedule override for the exact date REPLACES the weekday
#      schedule entirely (is_available=false or NULL times → blocked).
#   3. Otherwise the recurring weekly schedule(s) for that weekday.
# A doctor may have several schedule rows for one weekday (split
# shifts, e.g. 09:00-12:00 and 14:00-17:00) — every row contributes.
# ================================================================

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import AppointmentStatus, LeaveStatus
from app.models.appointment import Appointment
from app.models.doctor import (
    DoctorLeave,
    DoctorProfile,
    DoctorSchedule,
    DoctorScheduleOverride,
)
from app.utils.exceptions import NotFoundError

logger = logging.getLogger(__name__)

# Fallback slot length when neither the schedule nor the override
# specifies one. Matches the schema default for doctor_schedules.
DEFAULT_SLOT_DURATION_MINUTES = 15

# Appointment statuses that do NOT occupy a slot — a cancelled or
# no-show appointment frees its time for re-booking.
_FREEING_STATUSES = (
    AppointmentStatus.CANCELLED.value,
    AppointmentStatus.NO_SHOW.value,
)


# ----------------------------------------------------------------
# TIMEZONE + DATE HELPERS
# ----------------------------------------------------------------

def resolve_tz(tz_name: str) -> ZoneInfo:
    """Resolve an IANA timezone string, falling back to UTC on any
    empty or unrecognised value (v1 behaviour per the Phase 7 plan)."""
    if not tz_name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown hospital timezone, defaulting to UTC", extra={"tz": tz_name})
        return ZoneInfo("UTC")


def _schema_day_of_week(d: date) -> int:
    """Convert a date to the schema's day_of_week (0=Sunday..6=Saturday)."""
    return (d.weekday() + 1) % 7


def local_day_bounds_utc(target_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return the [start, end) UTC instants bounding a local calendar
    day. Used to filter TIMESTAMPTZ columns by a hospital-local date."""
    start_local = datetime.combine(target_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _window_slots(start: time, end: time, duration_minutes: int) -> list[tuple[time, time]]:
    """Slice a [start, end) window into back-to-back slots of the given
    length. A trailing partial slot that would overrun `end` is dropped."""
    slots: list[tuple[time, time]] = []
    cursor = datetime.combine(date.min, start)
    limit = datetime.combine(date.min, end)
    step = timedelta(minutes=duration_minutes)
    while cursor + step <= limit:
        nxt = cursor + step
        slots.append((cursor.time(), nxt.time()))
        cursor = nxt
    return slots


# ----------------------------------------------------------------
# BUILDING BLOCKS — reused by the appointment service for booking checks
# ----------------------------------------------------------------

async def load_doctor_scoped(
    db: AsyncSession, hospital_id: uuid.UUID, doctor_id: uuid.UUID
) -> DoctorProfile:
    """Load a doctor profile within the tenant. Cross-tenant access
    surfaces as NotFoundError (CLAUDE.md §13)."""
    result = await db.execute(
        select(DoctorProfile).where(
            DoctorProfile.id == doctor_id,
            DoctorProfile.hospital_id == hospital_id,
        )
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise NotFoundError("Doctor", doctor_id)
    return doctor


async def is_doctor_on_leave(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    target_date: date,
) -> bool:
    """True if an APPROVED leave covers target_date for this doctor."""
    result = await db.execute(
        select(DoctorLeave.id).where(
            DoctorLeave.doctor_id == doctor_id,
            DoctorLeave.hospital_id == hospital_id,
            DoctorLeave.status == LeaveStatus.APPROVED.value,
            DoctorLeave.start_date <= target_date,
            DoctorLeave.end_date >= target_date,
        )
    )
    return result.first() is not None


async def get_day_windows(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    target_date: date,
) -> list[tuple[time, time, int]]:
    """
    Return the doctor's working windows for target_date as
    (start_time, end_time, slot_duration_minutes) tuples.

    An empty list means the doctor is NOT working that date — either a
    blocking override, an override with NULL times, or no weekly
    schedule for that weekday. Leaves are NOT consulted here; callers
    that need leave handling must call is_doctor_on_leave separately.
    """
    override_result = await db.execute(
        select(DoctorScheduleOverride).where(
            DoctorScheduleOverride.doctor_id == doctor_id,
            DoctorScheduleOverride.hospital_id == hospital_id,
            DoctorScheduleOverride.override_date == target_date,
        )
    )
    override = override_result.scalar_one_or_none()
    if override is not None:
        if not override.is_available:
            return []
        if override.start_time is None or override.end_time is None:
            return []
        return [(
            override.start_time,
            override.end_time,
            override.slot_duration_minutes or DEFAULT_SLOT_DURATION_MINUTES,
        )]

    schedule_result = await db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.hospital_id == hospital_id,
            DoctorSchedule.day_of_week == _schema_day_of_week(target_date),
            DoctorSchedule.is_active.is_(True),
        )
    )
    return [
        (s.start_time, s.end_time, s.slot_duration_minutes or DEFAULT_SLOT_DURATION_MINUTES)
        for s in schedule_result.scalars().all()
    ]


async def get_booked_intervals(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    target_date: date,
    tz: ZoneInfo,
    *,
    exclude_appointment_id: uuid.UUID | None = None,
) -> list[tuple[datetime, datetime]]:
    """
    Return [start, end) tz-aware intervals for every appointment that
    occupies the doctor's time on target_date (hospital-local day).
    Cancelled and no-show appointments are excluded — they free the
    slot. exclude_appointment_id drops one row, used when an existing
    appointment is being rescheduled so it does not block itself.
    """
    day_start_utc, day_end_utc = local_day_bounds_utc(target_date, tz)
    conditions = [
        Appointment.doctor_id == doctor_id,
        Appointment.hospital_id == hospital_id,
        Appointment.deleted_at.is_(None),
        Appointment.status.not_in(_FREEING_STATUSES),
        Appointment.scheduled_at >= day_start_utc,
        Appointment.scheduled_at < day_end_utc,
    ]
    if exclude_appointment_id is not None:
        conditions.append(Appointment.id != exclude_appointment_id)

    result = await db.execute(select(Appointment).where(*conditions))
    intervals: list[tuple[datetime, datetime]] = []
    for appt in result.scalars().all():
        start_local = appt.scheduled_at.astimezone(tz)
        end_local = start_local + timedelta(minutes=appt.duration_minutes)
        intervals.append((start_local, end_local))
    return intervals


# ----------------------------------------------------------------
# PUBLIC — available slot listing
# ----------------------------------------------------------------

async def compute_available_slots(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    target_date: date,
    tz_name: str,
) -> list[dict]:
    """
    Return the doctor's free slots for target_date as a list of
    {start_time, end_time, available} dicts, sorted by start_time.

    Returns an empty list when the doctor is on approved leave, the day
    is blocked by an override, or there is no schedule for that weekday.
    All times are the hospital's local wall-clock (tz_name).
    """
    await load_doctor_scoped(db, hospital_id, doctor_id)
    tz = resolve_tz(tz_name)

    if await is_doctor_on_leave(db, hospital_id, doctor_id, target_date):
        return []

    windows = await get_day_windows(db, hospital_id, doctor_id, target_date)
    if not windows:
        return []

    candidates: list[tuple[time, time]] = []
    for w_start, w_end, duration in windows:
        candidates.extend(_window_slots(w_start, w_end, duration))
    if not candidates:
        return []

    booked = await get_booked_intervals(db, hospital_id, doctor_id, target_date, tz)

    available: list[dict] = []
    for slot_start, slot_end in candidates:
        start_dt = datetime.combine(target_date, slot_start, tzinfo=tz)
        end_dt = datetime.combine(target_date, slot_end, tzinfo=tz)
        overlaps = any(
            b_start < end_dt and b_end > start_dt for b_start, b_end in booked
        )
        if not overlaps:
            available.append(
                {"start_time": slot_start, "end_time": slot_end, "available": True}
            )

    available.sort(key=lambda s: s["start_time"])
    return available

# ================================================================
# NexusCare — app/services/doctor.py
# Doctor profile + schedules + leaves + overrides business logic.
# All queries are hospital-scoped.
#
# Deactivation model:
#   doctor_profiles has NO deleted_at column. "Deletion" is a flip
#   of is_active=False. The row is preserved (with all schedules,
#   leaves, history) so downstream visits / appointments keep their
#   FK targets intact. List endpoints exclude is_active=False by
#   default; GET still returns the inactive record so admins can
#   inspect or reactivate it.
#
# Reactivation is explicit. If a doctor profile already exists for
# (user_id, hospital_id) — active OR inactive — POST /doctors returns
# 409. The admin must PATCH with is_active=true to bring an old
# profile back, which prevents accidentally overwriting historical
# fields (specialization, fee, license_number) on a stale row.
#
# Tenant enforcement on sub-resources:
#   doctor_schedules / doctor_leaves / doctor_schedule_overrides each
#   carry their own hospital_id column but NO FK enforcing equality
#   with the parent doctor's hospital_id. Every sub-resource operation
#   therefore loads the parent doctor first via get_doctor(...) to
#   confirm tenant ownership before touching child rows.
#
# v2 deferred:
#   * Schedule overlap detection (two 9-12 and 11-2 entries on the same day)
#   * Leave overlap detection
#   * Permission-based role check (currently strict 'doctor' name match)
# ================================================================

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import LeaveStatus, UserRole
from app.models.doctor import (
    DoctorLeave,
    DoctorProfile,
    DoctorSchedule,
    DoctorScheduleOverride,
)
from app.models.hospital import Role
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.doctor import (
    DoctorCreate,
    DoctorUpdate,
    LeaveCreate,
    LeaveUpdate,
    OverrideCreate,
    OverrideUpdate,
    ScheduleCreate,
    ScheduleUpdate,
)
from app.utils.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# INTERNAL HELPERS
# ----------------------------------------------------------------

def _flatten_doctor(doctor: DoctorProfile) -> dict:
    """Build a dict combining DoctorProfile fields with the linked
    user's identity fields, suitable for DoctorResponse.model_validate."""
    user = doctor.user
    # TODO(phase7): use hospital.timezone instead of UTC. For v1 this
    # cutoff only feeds a display field; the appointments module is
    # where timezone correctness actually matters for booking.
    today_utc = datetime.now(timezone.utc).date()
    leaves_today = [
        leave
        for leave in doctor.leaves
        if leave.status == LeaveStatus.APPROVED.value and leave.end_date >= today_utc
    ]
    return {
        "id": doctor.id,
        "user_id": doctor.user_id,
        "hospital_id": doctor.hospital_id,
        "department_id": doctor.department_id,
        "specialization": doctor.specialization,
        "license_number": doctor.license_number,
        "consultation_fee": doctor.consultation_fee,
        "experience_years": doctor.experience_years,
        "bio": doctor.bio,
        "is_active": doctor.is_active,
        "created_at": doctor.created_at,
        "updated_at": doctor.updated_at,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "schedules": list(doctor.schedules),
        "active_leaves": leaves_today,
    }


def _list_item(doctor: DoctorProfile) -> dict:
    """Lean shape for DoctorListItem — pulls user.first_name/last_name."""
    return {
        "id": doctor.id,
        "user_id": doctor.user_id,
        "hospital_id": doctor.hospital_id,
        "first_name": doctor.user.first_name,
        "last_name": doctor.user.last_name,
        "specialization": doctor.specialization,
        "department_id": doctor.department_id,
        "consultation_fee": doctor.consultation_fee,
        "is_active": doctor.is_active,
        "created_at": doctor.created_at,
    }


async def _load_doctor(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> DoctorProfile:
    """Load a DoctorProfile with user, schedules, and leaves eagerly fetched.
    Cross-tenant access surfaces as NotFoundError."""
    result = await db.execute(
        select(DoctorProfile)
        .options(
            selectinload(DoctorProfile.user),
            selectinload(DoctorProfile.schedules),
            selectinload(DoctorProfile.leaves),
        )
        .where(
            DoctorProfile.id == doctor_id,
            DoctorProfile.hospital_id == hospital_id,
        )
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise NotFoundError("Doctor", doctor_id)
    return doctor


# ----------------------------------------------------------------
# DOCTOR PROFILE — READ
# ----------------------------------------------------------------

async def get_doctor(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> dict:
    """Returns the doctor flattened with user identity + nested schedules
    and currently-active approved leaves. Cross-tenant access → 404."""
    doctor = await _load_doctor(db, hospital_id, doctor_id)
    return _flatten_doctor(doctor)


async def list_doctors(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    q: Optional[str] = None,
    specialization: Optional[str] = None,
    department_id: Optional[uuid.UUID] = None,
    include_inactive: bool = False,
) -> dict:
    """
    Paginated doctor list, scoped to this hospital.

    Filters:
      * q                — ILIKE substring across user.first_name,
                           user.last_name, specialization, license_number.
      * specialization   — exact match.
      * department_id    — exact match.
      * include_inactive — when False (default), filters out is_active=False
                           doctors. Per the deactivation model above,
                           inactive doctors are kept on file forever.

    Ordering: created_at DESC. Most recently-onboarded doctor first —
    matches how Patient/User lists behave.
    """
    conditions = [DoctorProfile.hospital_id == hospital_id]
    if not include_inactive:
        conditions.append(DoctorProfile.is_active.is_(True))
    if specialization:
        conditions.append(DoctorProfile.specialization == specialization)
    if department_id:
        conditions.append(DoctorProfile.department_id == department_id)

    stmt = (
        select(DoctorProfile)
        .options(selectinload(DoctorProfile.user))
        .join(User, DoctorProfile.user_id == User.id)
        .where(and_(*conditions))
    )

    if q:
        q_term = f"%{q.strip()}%"
        if q_term != "%%":
            stmt = stmt.where(
                or_(
                    User.first_name.ilike(q_term),
                    User.last_name.ilike(q_term),
                    DoctorProfile.specialization.ilike(q_term),
                    DoctorProfile.license_number.ilike(q_term),
                )
            )

    stmt = stmt.order_by(DoctorProfile.created_at.desc())

    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(
        items=[_list_item(d) for d in items],
        total=total,
        page=page,
        size=size,
    )


async def count_doctors(db: AsyncSession, hospital_id: uuid.UUID) -> int:
    """Count of active doctors in this hospital. For future dashboards."""
    result = await db.execute(
        select(func.count(DoctorProfile.id)).where(
            DoctorProfile.hospital_id == hospital_id,
            DoctorProfile.is_active.is_(True),
        )
    )
    return int(result.scalar_one())


# ----------------------------------------------------------------
# DOCTOR PROFILE — CREATE / UPDATE / DEACTIVATE
# ----------------------------------------------------------------

async def _ensure_doctor_membership(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Confirms the target user has an active, non-deleted membership
    in this hospital with role.name == 'doctor'. Strict string match;
    custom roles like 'senior_doctor' are NOT accepted in v1.
    """
    result = await db.execute(
        select(HospitalMembership)
        .options(selectinload(HospitalMembership.role))
        .where(
            HospitalMembership.user_id == user_id,
            HospitalMembership.hospital_id == hospital_id,
            HospitalMembership.is_active.is_(True),
            HospitalMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise BadRequestError(
            "User is not a member of this hospital. Invite them first."
        )
    if membership.role.name != UserRole.DOCTOR.value:
        raise BadRequestError(
            f"User's role in this hospital is '{membership.role.name}', not 'doctor'. "
            "Change the membership role before creating a doctor profile."
        )


async def create_doctor(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    payload: DoctorCreate,
) -> dict:
    """
    Create a doctor profile for an existing user.

    Pre-conditions:
      * target user has an active 'doctor' membership in this hospital
      * no doctor profile already exists for (user_id, hospital_id),
        regardless of is_active — reactivation must be explicit (PATCH).
    """
    await _ensure_doctor_membership(db, hospital_id, payload.user_id)

    data = payload.model_dump()
    user_id = data.pop("user_id")

    doctor = DoctorProfile(hospital_id=hospital_id, user_id=user_id, **data)
    db.add(doctor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "Doctor profile already exists for user in hospital",
            extra={"hospital_id": str(hospital_id), "user_id": str(user_id)},
        )
        raise ConflictError(
            "This user already has a doctor profile in this hospital. "
            "Use PATCH to update or reactivate it."
        )

    logger.info(
        "Doctor created",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor.id),
            "user_id": str(user_id),
        },
    )
    return await get_doctor(db, hospital_id, doctor.id)


async def update_doctor(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    payload: DoctorUpdate,
) -> dict:
    """Partial update. user_id is not in the schema and cannot be changed."""
    doctor = await _load_doctor(db, hospital_id, doctor_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(doctor, field, value)

    await db.commit()
    logger.info(
        "Doctor updated",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
        },
    )
    return await get_doctor(db, hospital_id, doctor_id)


async def deactivate_doctor(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> None:
    """Flip is_active=False. The row is preserved; reactivate via PATCH."""
    doctor = await _load_doctor(db, hospital_id, doctor_id)
    doctor.is_active = False
    await db.commit()
    logger.info(
        "Doctor deactivated",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
        },
    )


# ----------------------------------------------------------------
# SCHEDULE (sub-resource)
# ----------------------------------------------------------------

async def add_schedule(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    payload: ScheduleCreate,
) -> DoctorSchedule:
    await _load_doctor(db, hospital_id, doctor_id)

    schedule = DoctorSchedule(
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        **payload.model_dump(),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    logger.info(
        "Schedule added",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "schedule_id": str(schedule.id),
        },
    )
    return schedule


async def list_schedules(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> list[DoctorSchedule]:
    """Returns schedules ordered by day_of_week, start_time for stable display."""
    doctor = await _load_doctor(db, hospital_id, doctor_id)
    return sorted(doctor.schedules, key=lambda s: (s.day_of_week, s.start_time))


async def update_schedule(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
) -> DoctorSchedule:
    await _load_doctor(db, hospital_id, doctor_id)

    result = await db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.id == schedule_id,
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.hospital_id == hospital_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundError("Schedule", schedule_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(schedule, field, value)

    # Re-check start < end after merging — Pydantic only enforces it
    # when both fields are present on the patch.
    if schedule.start_time >= schedule.end_time:
        await db.rollback()
        raise BadRequestError("start_time must be before end_time")

    await db.commit()
    await db.refresh(schedule)
    logger.info(
        "Schedule updated",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "schedule_id": str(schedule_id),
        },
    )
    return schedule


async def delete_schedule(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    schedule_id: uuid.UUID,
) -> None:
    """Hard delete — doctor_schedules has no deleted_at column."""
    await _load_doctor(db, hospital_id, doctor_id)

    result = await db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.id == schedule_id,
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.hospital_id == hospital_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundError("Schedule", schedule_id)

    await db.delete(schedule)
    await db.commit()
    logger.info(
        "Schedule deleted",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "schedule_id": str(schedule_id),
        },
    )


# ----------------------------------------------------------------
# LEAVE (sub-resource)
# ----------------------------------------------------------------

async def add_leave(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    payload: LeaveCreate,
) -> DoctorLeave:
    """Created leaves are always status='pending'; status transitions
    are routed through update_leave so approval audit can be captured."""
    await _load_doctor(db, hospital_id, doctor_id)

    leave = DoctorLeave(
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        **payload.model_dump(),
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    logger.info(
        "Leave requested",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "leave_id": str(leave.id),
        },
    )
    return leave


async def list_leaves(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    *,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[DoctorLeave]:
    """Returns leaves filtered by status / date overlap, ordered by start_date DESC."""
    await _load_doctor(db, hospital_id, doctor_id)

    conditions = [
        DoctorLeave.doctor_id == doctor_id,
        DoctorLeave.hospital_id == hospital_id,
    ]
    if status:
        conditions.append(DoctorLeave.status == status)
    if from_date:
        conditions.append(DoctorLeave.end_date >= from_date)
    if to_date:
        conditions.append(DoctorLeave.start_date <= to_date)

    result = await db.execute(
        select(DoctorLeave)
        .where(and_(*conditions))
        .order_by(DoctorLeave.start_date.desc())
    )
    return list(result.scalars().all())


async def update_leave(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    leave_id: uuid.UUID,
    payload: LeaveUpdate,
    *,
    current_user_id: uuid.UUID,
    current_membership_id: uuid.UUID,
) -> DoctorLeave:
    """
    Update a leave's dates / reason / status.

    Approval audit semantics:
      * Status transition to 'approved' → set approved_by / approved_by_membership_id.
      * Status transition to 'pending' or 'rejected' → clear them.
      * Date or reason edits without status change → audit fields are left untouched.
    """
    await _load_doctor(db, hospital_id, doctor_id)

    result = await db.execute(
        select(DoctorLeave).where(
            DoctorLeave.id == leave_id,
            DoctorLeave.doctor_id == doctor_id,
            DoctorLeave.hospital_id == hospital_id,
        )
    )
    leave = result.scalar_one_or_none()
    if leave is None:
        raise NotFoundError("Leave", leave_id)

    data = payload.model_dump(exclude_unset=True)
    new_status = data.get("status")

    for field, value in data.items():
        if field == "status":
            continue
        setattr(leave, field, value)

    if leave.start_date > leave.end_date:
        await db.rollback()
        raise BadRequestError("start_date must be on or before end_date")

    if new_status is not None:
        new_status_value = (
            new_status.value if hasattr(new_status, "value") else new_status
        )
        if new_status_value != leave.status:
            leave.status = new_status_value
            if new_status_value == LeaveStatus.APPROVED.value:
                leave.approved_by = current_user_id
                leave.approved_by_membership_id = current_membership_id
            else:
                leave.approved_by = None
                leave.approved_by_membership_id = None

    await db.commit()
    await db.refresh(leave)
    logger.info(
        "Leave updated",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "leave_id": str(leave_id),
            "status": leave.status,
        },
    )
    return leave


async def delete_leave(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    leave_id: uuid.UUID,
) -> None:
    """Hard delete — doctor_leaves has no deleted_at column."""
    await _load_doctor(db, hospital_id, doctor_id)

    result = await db.execute(
        select(DoctorLeave).where(
            DoctorLeave.id == leave_id,
            DoctorLeave.doctor_id == doctor_id,
            DoctorLeave.hospital_id == hospital_id,
        )
    )
    leave = result.scalar_one_or_none()
    if leave is None:
        raise NotFoundError("Leave", leave_id)

    await db.delete(leave)
    await db.commit()
    logger.info(
        "Leave deleted",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "leave_id": str(leave_id),
        },
    )


# ----------------------------------------------------------------
# OVERRIDE (sub-resource)
# ----------------------------------------------------------------

async def add_override(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    payload: OverrideCreate,
) -> DoctorScheduleOverride:
    """Create a one-off date override. UNIQUE(doctor_id, override_date)
    means at most one override per day; collisions surface as 409."""
    await _load_doctor(db, hospital_id, doctor_id)

    override = DoctorScheduleOverride(
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        **payload.model_dump(),
    )
    db.add(override)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "An override already exists for this doctor on this date. "
            "Use PATCH to modify it."
        )
    await db.refresh(override)
    logger.info(
        "Override added",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "override_id": str(override.id),
        },
    )
    return override


async def list_overrides(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[DoctorScheduleOverride]:
    """Returns overrides for this doctor, optionally bounded by date range,
    ordered by override_date ASC."""
    await _load_doctor(db, hospital_id, doctor_id)

    conditions = [
        DoctorScheduleOverride.doctor_id == doctor_id,
        DoctorScheduleOverride.hospital_id == hospital_id,
    ]
    if from_date:
        conditions.append(DoctorScheduleOverride.override_date >= from_date)
    if to_date:
        conditions.append(DoctorScheduleOverride.override_date <= to_date)

    result = await db.execute(
        select(DoctorScheduleOverride)
        .where(and_(*conditions))
        .order_by(DoctorScheduleOverride.override_date.asc())
    )
    return list(result.scalars().all())


async def update_override(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    override_id: uuid.UUID,
    payload: OverrideUpdate,
) -> DoctorScheduleOverride:
    await _load_doctor(db, hospital_id, doctor_id)

    result = await db.execute(
        select(DoctorScheduleOverride).where(
            DoctorScheduleOverride.id == override_id,
            DoctorScheduleOverride.doctor_id == doctor_id,
            DoctorScheduleOverride.hospital_id == hospital_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        raise NotFoundError("Override", override_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(override, field, value)

    # Post-merge consistency check (Pydantic only sees the patch fields).
    if override.is_available:
        if override.start_time is None or override.end_time is None:
            await db.rollback()
            raise BadRequestError(
                "start_time and end_time are required when is_available=true"
            )
        if override.start_time >= override.end_time:
            await db.rollback()
            raise BadRequestError("start_time must be before end_time")

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "An override already exists for this doctor on this date."
        )
    await db.refresh(override)
    logger.info(
        "Override updated",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "override_id": str(override_id),
        },
    )
    return override


async def delete_override(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    doctor_id: uuid.UUID,
    override_id: uuid.UUID,
) -> None:
    """Hard delete — doctor_schedule_overrides has no deleted_at column."""
    await _load_doctor(db, hospital_id, doctor_id)

    result = await db.execute(
        select(DoctorScheduleOverride).where(
            DoctorScheduleOverride.id == override_id,
            DoctorScheduleOverride.doctor_id == doctor_id,
            DoctorScheduleOverride.hospital_id == hospital_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        raise NotFoundError("Override", override_id)

    await db.delete(override)
    await db.commit()
    logger.info(
        "Override deleted",
        extra={
            "hospital_id": str(hospital_id),
            "doctor_id": str(doctor_id),
            "override_id": str(override_id),
        },
    )

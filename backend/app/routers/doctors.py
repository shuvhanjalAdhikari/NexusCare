# ================================================================
# NexusCare — app/routers/doctors.py
# Doctor profile CRUD + nested schedules / leaves / overrides.
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
#
# Authorization:
#   * Create / patch / deactivate doctor profile: HOSPITAL_ADMIN
#   * Add / patch / delete schedule:              HOSPITAL_ADMIN
#   * Approve / reject / mutate leave:            HOSPITAL_ADMIN
#       (a doctor can REQUEST their own leave via POST, but only an
#       admin can move it through pending/approved/rejected.)
#   * Add / patch / delete override:              HOSPITAL_ADMIN
#   * Read endpoints: any authenticated member of the hospital.
# ================================================================

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import LeaveStatus, UserRole
from app.database import get_db
from app.dependencies.auth import (
    get_current_membership,
    get_current_user,
    require_role,
)
from app.dependencies.hospital import get_hospital_id, get_hospital_timezone
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.appointment import SlotResponse
from app.schemas.doctor import (
    DoctorCreate,
    DoctorListResponse,
    DoctorResponse,
    DoctorUpdate,
    LeaveCreate,
    LeaveResponse,
    LeaveUpdate,
    OverrideCreate,
    OverrideResponse,
    OverrideUpdate,
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
)
from app.schemas.queue import TodayStatsResponse
from app.services import doctor as doctor_service
from app.services import queue as queue_service
from app.services import slot as slot_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/doctors", tags=["Doctors"])


# ----------------------------------------------------------------
# DOCTOR PROFILE CRUD
# ----------------------------------------------------------------

@router.post(
    "",
    response_model=DoctorResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def create_doctor(
    payload: DoctorCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await doctor_service.create_doctor(db, hospital_id, payload)


@router.get("", response_model=DoctorListResponse)
async def list_doctors(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    q: Optional[str] = Query(
        default=None,
        max_length=200,
        description="Substring match on first_name, last_name, specialization, license_number",
    ),
    specialization: Optional[str] = Query(
        default=None,
        max_length=150,
        description="Exact match on specialization",
    ),
    department_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by department"
    ),
    include_inactive: bool = Query(
        default=False,
        description="When true, include is_active=false doctors.",
    ),
):
    """Paginated doctor list scoped to this hospital."""
    return await doctor_service.list_doctors(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        q=q,
        specialization=specialization,
        department_id=department_id,
        include_inactive=include_inactive,
    )


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await doctor_service.get_doctor(db, hospital_id, doctor_id)


@router.patch(
    "/{doctor_id}",
    response_model=DoctorResponse,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def update_doctor(
    doctor_id: uuid.UUID,
    payload: DoctorUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await doctor_service.update_doctor(db, hospital_id, doctor_id, payload)


@router.delete(
    "/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def deactivate_doctor(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    await doctor_service.deactivate_doctor(db, hospital_id, doctor_id)


# ----------------------------------------------------------------
# SCHEDULES (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{doctor_id}/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def add_schedule(
    doctor_id: uuid.UUID,
    payload: ScheduleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await doctor_service.add_schedule(db, hospital_id, doctor_id, payload)


@router.get(
    "/{doctor_id}/schedules",
    response_model=list[ScheduleResponse],
)
async def list_schedules(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await doctor_service.list_schedules(db, hospital_id, doctor_id)


@router.patch(
    "/{doctor_id}/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def update_schedule(
    doctor_id: uuid.UUID,
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await doctor_service.update_schedule(
        db, hospital_id, doctor_id, schedule_id, payload
    )


@router.delete(
    "/{doctor_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def delete_schedule(
    doctor_id: uuid.UUID,
    schedule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    await doctor_service.delete_schedule(db, hospital_id, doctor_id, schedule_id)


# ----------------------------------------------------------------
# LEAVES (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{doctor_id}/leaves",
    response_model=LeaveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_leave(
    doctor_id: uuid.UUID,
    payload: LeaveCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Any authenticated hospital member may request a leave; status
    starts as 'pending' and only HOSPITAL_ADMIN can approve via PATCH."""
    return await doctor_service.add_leave(db, hospital_id, doctor_id, payload)


@router.get(
    "/{doctor_id}/leaves",
    response_model=list[LeaveResponse],
)
async def list_leaves(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    leave_status: Optional[LeaveStatus] = Query(
        default=None, alias="status", description="Filter by leave status"
    ),
    from_date: Optional[date] = Query(
        default=None, description="Include leaves ending on or after this date"
    ),
    to_date: Optional[date] = Query(
        default=None, description="Include leaves starting on or before this date"
    ),
):
    return await doctor_service.list_leaves(
        db,
        hospital_id,
        doctor_id,
        status=leave_status.value if leave_status else None,
        from_date=from_date,
        to_date=to_date,
    )


@router.patch(
    "/{doctor_id}/leaves/{leave_id}",
    response_model=LeaveResponse,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def update_leave(
    doctor_id: uuid.UUID,
    leave_id: uuid.UUID,
    payload: LeaveUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Status transitions to 'approved' stamp approved_by + approved_by_membership_id."""
    return await doctor_service.update_leave(
        db,
        hospital_id,
        doctor_id,
        leave_id,
        payload,
        current_user_id=current_user.id,
        current_membership_id=membership.id,
    )


@router.delete(
    "/{doctor_id}/leaves/{leave_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def delete_leave(
    doctor_id: uuid.UUID,
    leave_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    await doctor_service.delete_leave(db, hospital_id, doctor_id, leave_id)


# ----------------------------------------------------------------
# OVERRIDES (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{doctor_id}/overrides",
    response_model=OverrideResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def add_override(
    doctor_id: uuid.UUID,
    payload: OverrideCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await doctor_service.add_override(db, hospital_id, doctor_id, payload)


@router.get(
    "/{doctor_id}/overrides",
    response_model=list[OverrideResponse],
)
async def list_overrides(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    from_date: Optional[date] = Query(
        default=None, description="Include overrides on or after this date"
    ),
    to_date: Optional[date] = Query(
        default=None, description="Include overrides on or before this date"
    ),
):
    return await doctor_service.list_overrides(
        db, hospital_id, doctor_id, from_date=from_date, to_date=to_date
    )


@router.patch(
    "/{doctor_id}/overrides/{override_id}",
    response_model=OverrideResponse,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def update_override(
    doctor_id: uuid.UUID,
    override_id: uuid.UUID,
    payload: OverrideUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    return await doctor_service.update_override(
        db, hospital_id, doctor_id, override_id, payload
    )


@router.delete(
    "/{doctor_id}/overrides/{override_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.HOSPITAL_ADMIN))],
)
async def delete_override(
    doctor_id: uuid.UUID,
    override_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
):
    await doctor_service.delete_override(db, hospital_id, doctor_id, override_id)


# ----------------------------------------------------------------
# APPOINTMENT-FACING READ ENDPOINTS (Phase 7)
# These live here — rather than under /api/v1/appointments — because
# the URL is naturally nested under a doctor. The handlers delegate to
# the slot / queue services.
# ----------------------------------------------------------------

@router.get("/{doctor_id}/available-slots", response_model=list[SlotResponse])
async def get_available_slots(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
    slot_date: Annotated[date, Query(alias="date", description="Date to list slots for (YYYY-MM-DD)")],
):
    """Free appointment slots for a doctor on a date, in the hospital's
    local timezone. Empty when the doctor is on leave, the day is
    blocked by an override, or there is no schedule for that weekday."""
    return await slot_service.compute_available_slots(
        db, hospital_id, doctor_id, slot_date, tz_name
    )


@router.get("/{doctor_id}/today-stats", response_model=TodayStatsResponse)
async def get_today_stats(
    doctor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
):
    """Per-doctor OPD counts for the hospital's current local day."""
    return await queue_service.get_today_stats(db, hospital_id, doctor_id, tz_name)

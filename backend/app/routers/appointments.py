# ================================================================
# NexusCare — app/routers/appointments.py
# Appointment CRUD. Every route runs under get_current_user +
# get_hospital_id; cross-tenant access surfaces as NotFoundError
# (CLAUDE.md §13).
#
# Authorization: any authenticated member of the hospital may manage
# appointments (reception, nursing and admin all book) — mirrors the
# patient module. Role-scoped booking permissions are deferred to a
# later phase.
# ================================================================

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import AppointmentStatus
from app.database import get_db
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id, get_hospital_timezone
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentDetailResponse,
    AppointmentListResponse,
    AppointmentResponse,
    AppointmentUpdate,
)
from app.services import appointment as appointment_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/appointments", tags=["Appointments"])


# ----------------------------------------------------------------
# APPOINTMENT CRUD
# ----------------------------------------------------------------

@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment(
    payload: AppointmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
):
    """Book an appointment. appointment_type='walkin' is rejected —
    walk-ins enter the OPD queue via POST /api/v1/queue."""
    return await appointment_service.create_appointment(
        db,
        hospital_id,
        payload,
        booked_by=current_user.id,
        booked_by_membership_id=membership.id,
        tz_name=tz_name,
    )


@router.get("", response_model=AppointmentListResponse)
async def list_appointments(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    doctor_id: Optional[uuid.UUID] = Query(default=None, description="Filter by doctor"),
    patient_id: Optional[uuid.UUID] = Query(default=None, description="Filter by patient"),
    appointment_status: Optional[AppointmentStatus] = Query(
        default=None, alias="status", description="Filter by appointment status"
    ),
    from_date: Optional[datetime] = Query(
        default=None, description="Include appointments scheduled at or after this instant"
    ),
    to_date: Optional[datetime] = Query(
        default=None, description="Include appointments scheduled at or before this instant"
    ),
):
    """Paginated appointment list, ordered by scheduled_at ascending."""
    return await appointment_service.list_appointments(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        doctor_id=doctor_id,
        patient_id=patient_id,
        status=appointment_status.value if appointment_status else None,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{appointment_id}", response_model=AppointmentDetailResponse)
async def get_appointment(
    appointment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one appointment with embedded patient + doctor identity."""
    return await appointment_service.get_appointment_detail(
        db, hospital_id, appointment_id
    )


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
):
    """Partial update: status / scheduled_at / duration / department /
    notes. status=cancelled runs the queue cascade."""
    return await appointment_service.update_appointment(
        db, hospital_id, appointment_id, payload, tz_name=tz_name
    )


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Cancel an appointment — sets status='cancelled', stamps
    deleted_at, and cascades to the linked OPD queue entry."""
    await appointment_service.cancel_appointment(db, hospital_id, appointment_id)

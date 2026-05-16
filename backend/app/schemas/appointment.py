# ================================================================
# NexusCare — app/schemas/appointment.py
# Pydantic v2 schemas for the appointment module:
#   * Appointment CRUD + listing
#   * Available-slot listing (SlotResponse)
#
# hospital_id, booked_by, booked_by_membership_id are NEVER accepted
# from the request body:
#   * hospital_id comes from the JWT.
#   * booked_by / booked_by_membership_id come from the auth context.
#
# appointment_type='walkin' is rejected by the service layer with a
# BadRequestError — walk-ins are created via POST /api/v1/queue, not
# here. The enum still permits the value so the rejection can carry a
# helpful 400 message instead of a generic 422.
# ================================================================

from datetime import datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import AppointmentStatus, AppointmentType


# ----------------------------------------------------------------
# NESTED DETAIL SCHEMAS
# ----------------------------------------------------------------

class AppointmentPatientInfo(BaseModel):
    """Lean patient identity embedded in an appointment detail response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_number: str
    first_name: str
    last_name: str
    phone: Optional[str] = None


class AppointmentDoctorInfo(BaseModel):
    """Lean doctor identity embedded in an appointment detail response.
    Name fields are pulled from the linked User row by the service."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    specialization: Optional[str] = None


# ----------------------------------------------------------------
# APPOINTMENT SCHEMAS
# ----------------------------------------------------------------

class AppointmentBase(BaseModel):
    """Shared appointment fields between create and the flat response."""

    patient_id: UUID
    doctor_id: UUID
    department_id: Optional[UUID] = None
    appointment_type: AppointmentType = AppointmentType.NEW
    scheduled_at: datetime
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=480)
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    """Body for POST /api/v1/appointments.

    duration_minutes may be omitted — the service falls back to the
    doctor's schedule/override slot_duration for the requested day, or
    15 minutes if neither is defined."""


class AppointmentUpdate(BaseModel):
    """Body for PATCH /api/v1/appointments/{id}. All fields optional.

    status transitions are validated against the appointment state
    machine. checked_in / in_consultation / completed cannot be set
    here — they are driven by the OPD queue."""

    status: Optional[AppointmentStatus] = None
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=480)
    department_id: Optional[UUID] = None
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    """Flat appointment shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    patient_id: UUID
    doctor_id: UUID
    department_id: Optional[UUID] = None
    appointment_type: AppointmentType
    scheduled_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    notes: Optional[str] = None
    booked_by: Optional[UUID] = None
    booked_by_membership_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class AppointmentDetailResponse(AppointmentResponse):
    """Appointment with embedded patient + doctor identity. Returned by
    GET /api/v1/appointments/{id}. The nested objects are assembled by
    the service layer."""

    patient: AppointmentPatientInfo
    doctor: AppointmentDoctorInfo


# ----------------------------------------------------------------
# SLOT SCHEMAS
# ----------------------------------------------------------------

class SlotResponse(BaseModel):
    """A single bookable time slot for a doctor on a given date.
    Returned by GET /api/v1/doctors/{doctor_id}/available-slots."""

    start_time: time
    end_time: time
    available: bool = True


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

AppointmentListResponse = PagedResponse[AppointmentResponse]

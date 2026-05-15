# ================================================================
# NexusCare — app/schemas/doctor.py
# Pydantic v2 schemas for the doctor module:
#   * Doctor profile CRUD + listing
#   * Weekly schedules (sub-resource)
#   * Date-range leaves (sub-resource)
#   * One-off schedule overrides (sub-resource)
#
# hospital_id and user_id are NEVER accepted from update bodies:
#   * hospital_id comes from the JWT.
#   * user_id is set on create only and is identity-immutable thereafter.
#
# Schedule/leave/override overlap detection is deferred to v2 — for
# now the API trusts admins to enter sensible non-overlapping rows.
# ================================================================

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.constants.enums import LeaveStatus
from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# SCHEDULE SCHEMAS
# ----------------------------------------------------------------

class ScheduleBase(BaseModel):
    """Shared schedule fields. day_of_week: 0=Sunday, 6=Saturday."""

    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(default=15, ge=1, le=240)
    is_active: bool = True

    @model_validator(mode="after")
    def _start_before_end(self) -> "ScheduleBase":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ScheduleCreate(ScheduleBase):
    """Body for POST /api/v1/doctors/{doctor_id}/schedules."""


class ScheduleUpdate(BaseModel):
    """Body for PATCH /api/v1/doctors/{doctor_id}/schedules/{schedule_id}.
    All fields optional. If both times are provided, start < end is enforced."""

    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration_minutes: Optional[int] = Field(default=None, ge=1, le=240)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _start_before_end(self) -> "ScheduleUpdate":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValueError("start_time must be before end_time")
        return self


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    hospital_id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_minutes: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# LEAVE SCHEMAS
# ----------------------------------------------------------------

class LeaveBase(BaseModel):
    """Shared leave fields. status defaults to 'pending' at the DB layer."""

    start_date: date
    end_date: date
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _start_before_or_equal_end(self) -> "LeaveBase":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class LeaveCreate(LeaveBase):
    """Body for POST /api/v1/doctors/{doctor_id}/leaves.
    Created leaves are always status='pending'; admins move them via PATCH."""


class LeaveUpdate(BaseModel):
    """Body for PATCH /api/v1/doctors/{doctor_id}/leaves/{leave_id}.
    All fields optional. Approval audit (approved_by, approved_by_membership_id)
    is set server-side on transitions to 'approved'."""

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None
    status: Optional[LeaveStatus] = None

    @model_validator(mode="after")
    def _start_before_or_equal_end(self) -> "LeaveUpdate":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must be on or before end_date")
        return self


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    hospital_id: UUID
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: LeaveStatus
    approved_by: Optional[UUID] = None
    approved_by_membership_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# OVERRIDE SCHEMAS
# ----------------------------------------------------------------

class OverrideBase(BaseModel):
    """
    Shared override fields. Two valid shapes:
      * is_available=False → full-day block; start_time/end_time may be NULL.
      * is_available=True  → partial-day change; start_time/end_time required and start<end.
    """

    override_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration_minutes: Optional[int] = Field(default=None, ge=1, le=240)
    reason: Optional[str] = Field(default=None, max_length=200)
    is_available: bool = True

    @model_validator(mode="after")
    def _times_consistent(self) -> "OverrideBase":
        if self.is_available:
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    "start_time and end_time are required when is_available=true"
                )
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be before end_time")
        return self


class OverrideCreate(OverrideBase):
    """Body for POST /api/v1/doctors/{doctor_id}/overrides."""


class OverrideUpdate(BaseModel):
    """Body for PATCH /api/v1/doctors/{doctor_id}/overrides/{override_id}.
    All fields optional; consistency between is_available and times is re-checked
    in the service after merging with the existing row."""

    override_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration_minutes: Optional[int] = Field(default=None, ge=1, le=240)
    reason: Optional[str] = Field(default=None, max_length=200)
    is_available: Optional[bool] = None


class OverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    hospital_id: UUID
    override_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration_minutes: Optional[int] = None
    reason: Optional[str] = None
    is_available: bool
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# DOCTOR PROFILE SCHEMAS
# ----------------------------------------------------------------

class DoctorBase(BaseModel):
    """
    Shared doctor-profile fields (specialty, license, etc).
    User identity (first_name, last_name, email) lives on the User row
    and is never set via the doctor module — invite the user first.
    """

    department_id: Optional[UUID] = None
    specialization: Optional[str] = Field(default=None, max_length=150)
    license_number: Optional[str] = Field(default=None, max_length=100)
    consultation_fee: Optional[Decimal] = Field(default=None, ge=0)
    experience_years: Optional[int] = Field(default=None, ge=0, le=100)
    bio: Optional[str] = None


class DoctorCreate(DoctorBase):
    """Body for POST /api/v1/doctors.
    user_id must reference an existing user who already has an active
    'doctor' membership in this hospital."""

    user_id: UUID


class DoctorUpdate(BaseModel):
    """Body for PATCH /api/v1/doctors/{doctor_id}. user_id is omitted —
    identity is immutable; re-create the profile under a different user instead."""

    department_id: Optional[UUID] = None
    specialization: Optional[str] = Field(default=None, max_length=150)
    license_number: Optional[str] = Field(default=None, max_length=100)
    consultation_fee: Optional[Decimal] = Field(default=None, ge=0)
    experience_years: Optional[int] = Field(default=None, ge=0, le=100)
    bio: Optional[str] = None
    is_active: Optional[bool] = None


class DoctorResponse(DoctorBase):
    """
    Full doctor detail. Flattens the linked user's identity fields onto
    the doctor so the UI does not need a second fetch. Includes the full
    weekly schedule and any currently-active approved leaves.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    hospital_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Flattened user fields (populated by service layer)
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None

    schedules: list[ScheduleResponse] = Field(default_factory=list)
    active_leaves: list[LeaveResponse] = Field(default_factory=list)


class DoctorListItem(BaseModel):
    """Lean row for list/search endpoints — no schedules, no leaves, no bio."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    hospital_id: UUID
    first_name: str
    last_name: str
    specialization: Optional[str] = None
    department_id: Optional[UUID] = None
    consultation_fee: Optional[Decimal] = None
    is_active: bool
    created_at: datetime


DoctorListResponse = PagedResponse[DoctorListItem]

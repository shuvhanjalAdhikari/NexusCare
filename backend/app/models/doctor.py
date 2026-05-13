# ================================================================
# NexusCare — app/models/doctor.py
# Departments, doctor profiles, schedules, leaves, and overrides.
# ================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, SmallInteger, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.hospital import Hospital
    from app.models.user import User
    from app.models.appointment import Appointment
    from app.models.visit import Visit


# ----------------------------------------------------------------
# DEPARTMENT
# ----------------------------------------------------------------

class Department(Base):
    """An organisational unit within a hospital (e.g. Cardiology, Paediatrics)."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    hospital: Mapped[Hospital] = relationship("Hospital", back_populates="departments")
    doctors: Mapped[list[DoctorProfile]] = relationship("DoctorProfile", back_populates="department")


# ----------------------------------------------------------------
# DOCTOR PROFILE
# ----------------------------------------------------------------

class DoctorProfile(Base):
    """
    Extended profile for a doctor at a specific hospital.
    Unique per (user_id, hospital_id) — a doctor working at two hospitals
    has two separate profiles (different fee, schedule, license per hospital).
    """

    __tablename__ = "doctor_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "hospital_id", name="uq_doctor_profile_user_hospital"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True
    )
    specialization: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    license_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    consultation_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    experience_years: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="doctor_profiles")
    department: Mapped[Optional[Department]] = relationship("Department", back_populates="doctors")
    schedules: Mapped[list[DoctorSchedule]] = relationship(
        "DoctorSchedule", back_populates="doctor", cascade="all, delete-orphan"
    )
    leaves: Mapped[list[DoctorLeave]] = relationship(
        "DoctorLeave", back_populates="doctor", cascade="all, delete-orphan"
    )
    schedule_overrides: Mapped[list[DoctorScheduleOverride]] = relationship(
        "DoctorScheduleOverride", back_populates="doctor", cascade="all, delete-orphan"
    )
    appointments: Mapped[list[Appointment]] = relationship("Appointment", back_populates="doctor")
    visits: Mapped[list[Visit]] = relationship("Visit", back_populates="doctor")


# ----------------------------------------------------------------
# DOCTOR SCHEDULE
# ----------------------------------------------------------------

class DoctorSchedule(Base):
    """
    A recurring weekly availability slot for a doctor.
    day_of_week: 0 = Sunday, 6 = Saturday.
    """

    __tablename__ = "doctor_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="15")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    doctor: Mapped[DoctorProfile] = relationship("DoctorProfile", back_populates="schedules")


# ----------------------------------------------------------------
# DOCTOR LEAVE
# ----------------------------------------------------------------

class DoctorLeave(Base):
    """
    A leave request for a doctor covering a date range.
    Approved leaves block appointment booking for the covered dates.
    """

    __tablename__ = "doctor_leaves"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_by_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospital_memberships.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    doctor: Mapped[DoctorProfile] = relationship("DoctorProfile", back_populates="leaves")


# ----------------------------------------------------------------
# DOCTOR SCHEDULE OVERRIDE
# ----------------------------------------------------------------

class DoctorScheduleOverride(Base):
    """
    A one-off exception to a doctor's regular schedule for a specific date.
    is_available=False blocks the entire day; optional times narrow the block.
    Unique per (doctor_id, override_date).
    """

    __tablename__ = "doctor_schedule_overrides"
    __table_args__ = (
        UniqueConstraint("doctor_id", "override_date", name="uq_doctor_override_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    override_date: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL start_time/end_time means the full day is blocked
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    slot_duration_minutes: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    doctor: Mapped[DoctorProfile] = relationship("DoctorProfile", back_populates="schedule_overrides")

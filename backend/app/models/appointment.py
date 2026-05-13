# ================================================================
# NexusCare — app/models/appointment.py
# Appointments and real-time OPD queue entries.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.doctor import DoctorProfile
    from app.models.visit import Visit


class Appointment(Base):
    """
    A scheduled or walk-in patient appointment with a doctor.
    Soft-deleted via deleted_at.
    """

    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=False, index=True
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    appointment_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="15")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="scheduled")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    booked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    booked_by_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospital_memberships.id"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    patient: Mapped[Patient] = relationship("Patient", back_populates="appointments")
    doctor: Mapped[DoctorProfile] = relationship("DoctorProfile", back_populates="appointments")
    queue_entry: Mapped[Optional[OPDQueue]] = relationship("OPDQueue", back_populates="appointment", uselist=False)
    visit: Mapped[Optional[Visit]] = relationship("Visit", back_populates="appointment", uselist=False)


class OPDQueue(Base):
    """
    Real-time queue position for a patient on a given day.
    Walk-in entries have appointment_id = NULL.
    Hard-deleted when the queue is cleared (no soft delete).
    """

    __tablename__ = "opd_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL for walk-in patients who have no prior appointment
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=False, index=True
    )
    queue_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default="normal")
    status: Mapped[str] = mapped_column(String(25), nullable=False, server_default="waiting")
    counter_no: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    estimated_wait_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checked_in_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    called_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    appointment: Mapped[Optional[Appointment]] = relationship("Appointment", back_populates="queue_entry")

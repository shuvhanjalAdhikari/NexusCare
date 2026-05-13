# ================================================================
# NexusCare — app/models/visit.py
# Clinical visit layer: SOAP notes, vitals, diagnoses, referrals.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.doctor import DoctorProfile
    from app.models.appointment import Appointment
    from app.models.prescription import Prescription
    from app.models.lab import LabOrder
    from app.models.followup import Followup


# ----------------------------------------------------------------
# VISIT
# ----------------------------------------------------------------

class Visit(Base):
    """
    A clinical encounter between a patient and doctor.
    Contains SOAP notes inline. Soft-deleted via deleted_at.
    """

    __tablename__ = "visits"

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
    # Nullable — walk-in visits have no appointment
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    queue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opd_queue.id"), nullable=True
    )
    # SOAP clinical notes
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    examination_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assessment_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="waiting")
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospital_memberships.id"), nullable=True
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_by_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospital_memberships.id"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)

    # Relationships
    patient: Mapped[Patient] = relationship("Patient", back_populates="visits")
    doctor: Mapped[DoctorProfile] = relationship("DoctorProfile", back_populates="visits")
    appointment: Mapped[Optional[Appointment]] = relationship("Appointment", back_populates="visit")
    vitals: Mapped[list[Vital]] = relationship(
        "Vital", back_populates="visit", cascade="all, delete-orphan"
    )
    diagnoses: Mapped[list[VisitDiagnosis]] = relationship(
        "VisitDiagnosis", back_populates="visit", cascade="all, delete-orphan"
    )
    referrals: Mapped[list[Referral]] = relationship("Referral", back_populates="visit")
    prescriptions: Mapped[list[Prescription]] = relationship("Prescription", back_populates="visit")
    lab_orders: Mapped[list[LabOrder]] = relationship("LabOrder", back_populates="visit")
    followups: Mapped[list[Followup]] = relationship("Followup", back_populates="visit")


# ----------------------------------------------------------------
# VITALS
# ----------------------------------------------------------------

class Vital(Base):
    """Nurse-recorded vitals snapshot for a visit. Cascades on visit delete."""

    __tablename__ = "vitals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    bp_systolic: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    bp_diastolic: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    heart_rate: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    temperature: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    spo2: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    height_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    # Stored even though computed — preserves a snapshot at time of recording
    bmi: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    # 1 = Immediate (life-threatening) … 5 = Non-urgent (routine)
    triage_level: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    recorded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    recorded_by_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospital_memberships.id"), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    visit: Mapped[Visit] = relationship("Visit", back_populates="vitals")


# ----------------------------------------------------------------
# VISIT DIAGNOSIS
# ----------------------------------------------------------------

class VisitDiagnosis(Base):
    """
    A diagnosis recorded during a visit. A visit can have multiple diagnoses
    (primary, secondary, differential). Cascades on visit delete.

    Note: the DB column is named 'type' but the Python attribute is
    'diagnosis_type' to avoid conflict with SQLAlchemy's polymorphic internals.
    """

    __tablename__ = "visit_diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    icd_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    diagnosis_text: Mapped[str] = mapped_column(String(500), nullable=False)
    diagnosis_type: Mapped[str] = mapped_column("type", String(20), nullable=False, server_default="primary")
    is_chronic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    visit: Mapped[Visit] = relationship("Visit", back_populates="diagnoses")


# ----------------------------------------------------------------
# REFERRAL
# ----------------------------------------------------------------

class Referral(Base):
    """
    A referral generated during a visit — either to another doctor in the same
    hospital (internal) or to an external facility.

    Two FKs to doctor_profiles (from_doctor_id, to_doctor_id) require explicit
    foreign_keys on any relationship to avoid SQLAlchemy join ambiguity.
    Here we expose them as plain FK columns; navigation is done via service queries.
    """

    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True
    )
    from_doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=False
    )
    # NULL when referral is to an external facility
    to_doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=True
    )
    to_department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    referral_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_hospital: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False, server_default="routine")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    visit: Mapped[Visit] = relationship("Visit", back_populates="referrals")

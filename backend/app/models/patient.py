# ================================================================
# NexusCare — app/models/patient.py
# Patient registration and allergy records.
# ================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.visit import Visit
    from app.models.billing import Invoice


class Patient(Base):
    """
    A patient registered in a hospital. Never hard-deleted — soft-delete only.
    patient_number is unique per hospital (hospital assigns their own numbering).
    """

    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("hospital_id", "patient_number", name="uq_patient_hospital_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dob: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    blood_group: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    emergency_contact_relationship: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    allergies: Mapped[list[PatientAllergy]] = relationship(
        "PatientAllergy", back_populates="patient", cascade="all, delete-orphan"
    )
    appointments: Mapped[list[Appointment]] = relationship("Appointment", back_populates="patient")
    visits: Mapped[list[Visit]] = relationship("Visit", back_populates="patient")
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="patient")


class PatientAllergy(Base):
    """Allergy record for a patient. Cascades on patient delete."""

    __tablename__ = "patient_allergies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    allergen: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reaction: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    patient: Mapped[Patient] = relationship("Patient", back_populates="allergies")

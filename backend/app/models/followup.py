# ================================================================
# NexusCare — app/models/followup.py
# Scheduled follow-ups and patient feedback.
# ================================================================

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.visit import Visit


class Followup(Base):
    """A follow-up visit recommended by a doctor at the end of a clinical visit."""

    __tablename__ = "followups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=False, index=True
    )
    recommended_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    visit: Mapped[Visit] = relationship("Visit", back_populates="followups")


class Feedback(Base):
    """
    Patient satisfaction feedback submitted after an appointment.
    No created_at/updated_at — only submitted_at.
    """

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=True
    )
    rating_overall: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    rating_doctor: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    rating_wait_time: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    rating_cleanliness: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    submitted_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

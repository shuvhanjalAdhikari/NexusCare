# ================================================================
# NexusCare — app/models/lab.py
# Lab test catalogue, orders, and results.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.visit import Visit


class LabTest(Base):
    """
    Hospital's normalised lab test catalogue entry.
    Orders reference a test by FK rather than storing free-text names.
    """

    __tablename__ = "lab_tests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sample_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tat_hours: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    reference_range: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    orders: Mapped[list[LabOrder]] = relationship("LabOrder", back_populates="test")


class LabOrder(Base):
    """
    A lab test order raised during a visit.
    Status progresses: ordered → collected → in_progress → result_ready → reviewed | cancelled.
    """

    __tablename__ = "lab_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=False, index=True
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_tests.id"), nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default="routine")
    status: Mapped[str] = mapped_column(String(25), nullable=False, server_default="ordered")
    sample_collected_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    result_ready_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    visit: Mapped[Visit] = relationship("Visit", back_populates="lab_orders")
    test: Mapped[LabTest] = relationship("LabTest", back_populates="orders")
    result: Mapped[Optional[LabResult]] = relationship(
        "LabResult", back_populates="order", uselist=False
    )


class LabResult(Base):
    """
    The result for a lab order. One-to-one with LabOrder (lab_order_id is UNIQUE).
    Cascades on lab order delete.
    """

    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lab_orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    result_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reference_range: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_abnormal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    file_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    order: Mapped[LabOrder] = relationship("LabOrder", back_populates="result")

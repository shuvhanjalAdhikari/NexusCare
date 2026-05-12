# ================================================================
# NexusCare — app/models/user.py
# Staff user accounts. Each user belongs to exactly one hospital.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.hospital import Hospital, Role
    from app.models.doctor import DoctorProfile


class User(Base):
    """
    A staff member of a hospital — doctor, nurse, receptionist, etc.
    Soft-deleted via deleted_at; never hard-deleted.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("hospital_id", "email", name="uq_user_hospital_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    hospital: Mapped[Hospital] = relationship("Hospital", back_populates="users")
    role: Mapped[Role] = relationship("Role", back_populates="users")
    doctor_profile: Mapped[Optional[DoctorProfile]] = relationship(
        "DoctorProfile", back_populates="user", uselist=False
    )

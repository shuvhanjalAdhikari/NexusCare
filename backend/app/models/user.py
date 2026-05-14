# ================================================================
# NexusCare — app/models/user.py
# Global user account. Not tied to any single hospital.
# Hospital membership and role live on HospitalMembership.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.membership import HospitalMembership
    from app.models.doctor import DoctorProfile


class User(Base):
    """
    A platform-level user account. One account per person, globally unique by email.
    Hospital membership, role, and tenant context live on HospitalMembership.
    Soft-deleted via deleted_at; never hard-deleted.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Only set for NexusCare platform accounts (e.g. 'super_admin'). NULL for all hospital staff.
    system_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    memberships: Mapped[list[HospitalMembership]] = relationship(
        "HospitalMembership",
        foreign_keys="HospitalMembership.user_id",
        back_populates="user",
    )
    doctor_profiles: Mapped[list[DoctorProfile]] = relationship(
        "DoctorProfile", back_populates="user"
    )

# ================================================================
# NexusCare — app/models/membership.py
# Links a global user account to a hospital with a specific role.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.hospital import Hospital, Role


class HospitalMembership(Base):
    """
    Scopes a user to a hospital with a specific role.
    A user can belong to multiple hospitals simultaneously, each with its own role.
    Soft-deleted via deleted_at to preserve the 'member from X to Y' audit trail.
    is_active allows temporary suspension without ending the membership.
    """

    __tablename__ = "hospital_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "hospital_id", name="uq_membership_user_hospital"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Audit: who granted this membership
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

    # Relationships
    user: Mapped[User] = relationship(
        "User", foreign_keys=[user_id], back_populates="memberships"
    )
    hospital: Mapped[Hospital] = relationship("Hospital", back_populates="memberships")
    role: Mapped[Role] = relationship("Role", back_populates="memberships")

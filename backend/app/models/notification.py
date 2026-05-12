# ================================================================
# NexusCare — app/models/notification.py
# In-app, email, SMS, and push notifications.
# ================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

TIMESTAMPTZ = TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    """
    A notification sent to a user via one or more channels.
    Hard-deleted when cleared — no soft delete, no updated_at.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sent_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    # Python attribute renamed to avoid conflict with SQLAlchemy's reserved Base.metadata
    meta: Mapped[Optional[Any]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default="now()")

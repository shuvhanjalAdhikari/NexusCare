# ================================================================
# NexusCare — app/schemas/notification.py
# Pydantic v2 schemas for in-app notifications.
#
# There is no public create schema — notifications are produced by
# the internal create_notification() service helper. The only HTTP
# create path is the super-admin debug endpoint, backed by
# NotificationAdminCreate below.
#
# The JSONB column 'metadata' is exposed in the API as 'meta' — a
# field literally named 'metadata' would collide with SQLAlchemy's
# Base.metadata when Pydantic reads attributes via from_attributes.
# ================================================================

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import NotificationChannel
from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# CREATE (super-admin debug endpoint only)
# ----------------------------------------------------------------

class NotificationAdminCreate(BaseModel):
    """
    Body for POST /api/v1/admin/notifications (super-admin only).

    hospital_id and user_id ARE accepted in the body here — the one
    documented exception to "never accept hospital_id in a body"
    (CLAUDE.md §5). A super-admin request carries no tenant-scoped
    JWT, so the target tenant/user must come from the body. The
    service verifies user_id is a member of hospital_id before insert.
    """

    hospital_id: UUID
    user_id: UUID
    type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    body: Optional[str] = None
    channel: NotificationChannel = NotificationChannel.IN_APP
    # entity_type / entity_id are packed into the meta JSONB by the
    # service — the notifications table has no dedicated columns.
    entity_type: Optional[str] = Field(default=None, max_length=50)
    entity_id: Optional[UUID] = None
    meta: Optional[dict[str, Any]] = None


# ----------------------------------------------------------------
# RESPONSE
# ----------------------------------------------------------------

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    user_id: Optional[UUID]
    type: str
    title: str
    body: Optional[str]
    channel: str
    is_read: bool
    sent_at: Optional[datetime]
    read_at: Optional[datetime]
    # Exposed as 'meta'; the underlying column is 'metadata'.
    meta: Optional[dict[str, Any]]
    created_at: datetime


NotificationListResponse = PagedResponse[NotificationResponse]


class UnreadCountResponse(BaseModel):
    """Response for GET /api/v1/notifications/me/unread-count."""

    unread_count: int


class MarkAllReadResponse(BaseModel):
    """Response for PATCH /api/v1/notifications/me/mark-all-read."""

    marked_read: int

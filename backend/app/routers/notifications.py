# ================================================================
# NexusCare — app/routers/notifications.py
# Two router objects:
#   * router        — /api/v1/notifications/me  (the caller's own
#                     notifications: list, count, mark-read, dismiss)
#   * admin_router  — /api/v1/admin/notifications  (super-admin debug
#                     POST to seed notifications; no public create
#                     endpoint exists in v1)
#
# Every /me route runs under get_current_user + get_hospital_id and is
# scoped to the calling user — a user never sees another user's
# notifications (CLAUDE.md §13, cross-user defense).
# ================================================================

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, require_super_admin
from app.dependencies.hospital import get_hospital_id
from app.models.user import User
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationAdminCreate,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services import notification as notification_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

admin_router = APIRouter(
    prefix="/api/v1/admin/notifications",
    tags=["Admin"],
    dependencies=[Depends(require_super_admin)],
)


# ----------------------------------------------------------------
# MY NOTIFICATIONS
# ----------------------------------------------------------------

@router.get("/me", response_model=NotificationListResponse)
async def list_my_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    is_read: Optional[bool] = Query(
        default=None, description="Filter by read state"
    ),
    type: Optional[str] = Query(
        default=None, max_length=80, description="Exact match on notification type"
    ),
):
    """
    Paginated list of the caller's own notifications in this hospital,
    newest first. Never returns another user's notifications.
    """
    return await notification_service.list_my_notifications(
        db,
        hospital_id,
        current_user.id,
        pagination.page,
        pagination.size,
        is_read=is_read,
        type=type,
    )


@router.get("/me/unread-count", response_model=UnreadCountResponse)
async def my_unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Quick unread count for the header badge."""
    count = await notification_service.unread_count(
        db, hospital_id, current_user.id
    )
    return UnreadCountResponse(unread_count=count)


@router.patch("/me/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Mark all of the caller's notifications read. Idempotent."""
    marked = await notification_service.mark_all_read(
        db, hospital_id, current_user.id
    )
    return MarkAllReadResponse(marked_read=marked)


@router.patch("/me/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Mark a single notification read."""
    return await notification_service.mark_read(
        db, hospital_id, current_user.id, notification_id
    )


@router.delete("/me/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_notification(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Dismiss (hard-delete) one of the caller's notifications."""
    await notification_service.dismiss_notification(
        db, hospital_id, current_user.id, notification_id
    )


# ----------------------------------------------------------------
# SUPER-ADMIN — debug create
# ----------------------------------------------------------------

@admin_router.post(
    "",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_notification(
    payload: NotificationAdminCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Super-admin-only: create a notification for any user. Used to seed
    test/debug data without modifying other services. The target user
    must be a member of the target hospital.
    """
    return await notification_service.admin_create_notification(db, payload)

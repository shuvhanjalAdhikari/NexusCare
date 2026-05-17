# ================================================================
# NexusCare — app/services/notification.py
# In-app notification business logic.
#
# Notifications are produced two ways:
#   1. Internally — other services call create_notification() when an
#      action warrants an alert (e.g. lab.complete → "Lab result
#      ready"). No public POST endpoint exists for this in v1.
#   2. Via the super-admin debug endpoint — admin_create_notification()
#      backs POST /api/v1/admin/notifications, used to seed test data.
#
# meta JSONB convention
# ---------------------
# The notifications table has NO entity_type / entity_id columns. To
# deep-link a notification to a resource, callers pass entity_type and
# entity_id to create_notification(); they are packed into the meta
# JSONB as {"entity_type": "<str>", "entity_id": "<uuid-str>"}. Any
# extra dict passed as meta_extra is merged in alongside. The stored
# meta is NULL when nothing is supplied.
#
# Read access is doubly defended: every /me query filters by
# user_id == caller (cross-user) AND hospital_id == JWT hospital
# (cross-tenant). A user never sees another user's notifications.
#
# Notifications are hard-deleted and have no updated_at — mark-read
# simply stamps the row and commits.
# ================================================================

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import NotificationChannel
from app.models.membership import HospitalMembership
from app.models.notification import Notification
from app.schemas.notification import NotificationAdminCreate
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# CREATE — internal helper + super-admin endpoint backing
# ----------------------------------------------------------------

async def create_notification(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: Optional[str] = None,
    channel: str = NotificationChannel.IN_APP.value,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    meta_extra: Optional[dict[str, Any]] = None,
    sent_at: Optional[datetime] = None,
) -> Notification:
    """
    Internal notification factory — call this from any service that
    needs to raise an in-app alert.

    entity_type / entity_id are packed into the meta JSONB (see the
    module docstring for the shape). meta_extra is merged in alongside.
    """
    meta: dict[str, Any] = {}
    if entity_type is not None:
        meta["entity_type"] = entity_type
    if entity_id is not None:
        meta["entity_id"] = str(entity_id)
    if meta_extra:
        meta.update(meta_extra)

    notification = Notification(
        hospital_id=hospital_id,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        channel=channel,
        meta=meta or None,
        sent_at=sent_at,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    logger.info(
        "Notification created",
        extra={
            "hospital_id": str(hospital_id),
            "notification_id": str(notification.id),
        },
    )
    return notification


async def admin_create_notification(
    db: AsyncSession, payload: NotificationAdminCreate
) -> Notification:
    """
    Backing for the super-admin debug endpoint. Verifies the target
    user has an active, non-deleted membership in the target hospital
    before inserting — a super-admin must not create cross-tenant
    notification noise.
    """
    result = await db.execute(
        select(HospitalMembership.id).where(
            HospitalMembership.user_id == payload.user_id,
            HospitalMembership.hospital_id == payload.hospital_id,
            HospitalMembership.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        logger.warning(
            "Rejected admin notification — target user not in hospital",
            extra={"hospital_id": str(payload.hospital_id)},
        )
        raise BadRequestError(
            "Target user is not a member of the target hospital."
        )

    return await create_notification(
        db,
        payload.hospital_id,
        user_id=payload.user_id,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        channel=payload.channel.value,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        meta_extra=payload.meta,
    )


# ----------------------------------------------------------------
# READ — always scoped to the calling user
# ----------------------------------------------------------------

async def list_my_notifications(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    page: int,
    size: int,
    *,
    is_read: Optional[bool] = None,
    type: Optional[str] = None,
) -> dict:
    """
    Paginated list of the caller's notifications in this hospital,
    newest first. Filtered by user_id (cross-user defense) AND
    hospital_id (cross-tenant defense) — both layers, always.
    """
    conditions = [
        Notification.user_id == user_id,
        Notification.hospital_id == hospital_id,
    ]
    if is_read is not None:
        conditions.append(Notification.is_read.is_(is_read))
    if type is not None:
        conditions.append(Notification.type == type)

    stmt = (
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


async def unread_count(
    db: AsyncSession, hospital_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    """Count of the caller's unread notifications — header badge."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.hospital_id == hospital_id,
            Notification.is_read.is_(False),
        )
    )
    return int(result.scalar_one())


async def _get_my_notification(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> Notification:
    """
    Load one notification owned by the caller. A notification belonging
    to another user or hospital surfaces as NotFoundError — existence
    is never leaked across users or tenants.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.hospital_id == hospital_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise NotFoundError("Notification", notification_id)
    return notification


# ----------------------------------------------------------------
# MARK READ / DISMISS
# ----------------------------------------------------------------

async def mark_read(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> Notification:
    """Mark a single notification read. Idempotent — re-marking is a no-op."""
    notification = await _get_my_notification(
        db, hospital_id, user_id, notification_id
    )
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)
    return notification


async def mark_all_read(
    db: AsyncSession, hospital_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    """
    Mark every unread notification of the caller read. Scoped to
    user_id AND hospital_id. Idempotent — returns 0 when nothing was
    unread. Returns the number of rows updated.
    """
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.hospital_id == hospital_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    marked = int(result.rowcount or 0)
    logger.info(
        "Notifications marked read",
        extra={"hospital_id": str(hospital_id), "marked_read": marked},
    )
    return marked


async def dismiss_notification(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> None:
    """Hard delete — notifications have no deleted_at column."""
    notification = await _get_my_notification(
        db, hospital_id, user_id, notification_id
    )
    await db.delete(notification)
    await db.commit()
    logger.info(
        "Notification dismissed",
        extra={
            "hospital_id": str(hospital_id),
            "notification_id": str(notification_id),
        },
    )

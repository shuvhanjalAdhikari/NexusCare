# ================================================================
# NexusCare — app/routers/feedback.py
# Patient satisfaction feedback — /api/v1/feedback.
#
# POST is the inbound endpoint: any authenticated hospital member may
# submit feedback (staff enter it on the patient's behalf at the
# counter or via a tablet — v1 has no patient portal). Listing and
# retrieval are open to any member; DELETE is hospital-admin only.
#
# Feedback is immutable — there is no PATCH route. Corrections are
# made by deleting and re-creating.
#
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
# ================================================================

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import UserRole
from app.database import get_db
from app.dependencies.auth import get_current_user, require_role
from app.dependencies.hospital import get_hospital_id
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
)
from app.services import feedback as feedback_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/feedback", tags=["Feedback"])

# Hospital-admin guard reused by the DELETE route.
_require_admin = require_role(UserRole.HOSPITAL_ADMIN)


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(
    payload: FeedbackCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Submit a feedback record. patient_id is required (see schema)."""
    return await feedback_service.create_feedback(db, hospital_id, payload)


# ----------------------------------------------------------------
# LIST / GET
# ----------------------------------------------------------------

@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    doctor_id: Optional[uuid.UUID] = Query(default=None),
    min_rating: Optional[int] = Query(
        default=None, ge=1, le=5, description="Lower bound on rating_overall"
    ),
    max_rating: Optional[int] = Query(
        default=None, ge=1, le=5, description="Upper bound on rating_overall"
    ),
    from_date: Optional[datetime] = Query(
        default=None, description="Lower bound on submitted_at (inclusive)"
    ),
    to_date: Optional[datetime] = Query(
        default=None, description="Upper bound on submitted_at (inclusive)"
    ),
):
    """Paginated feedback list scoped to this hospital, newest first."""
    return await feedback_service.list_feedback(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        doctor_id=doctor_id,
        min_rating=min_rating,
        max_rating=max_rating,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(
    feedback_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await feedback_service.get_feedback(db, hospital_id, feedback_id)


# ----------------------------------------------------------------
# DELETE — hospital-admin only
# ----------------------------------------------------------------

@router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    feedback_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[HospitalMembership, Depends(_require_admin)],
):
    """Hard-delete a feedback entry. Rare correction path; admins only."""
    await feedback_service.delete_feedback(db, hospital_id, feedback_id)

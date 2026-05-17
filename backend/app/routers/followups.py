# ================================================================
# NexusCare — app/routers/followups.py
# Two router objects:
#   * router                — /api/v1/followups  (list, get, update,
#                             delete)
#   * visit_followups_router — /api/v1/visits/{visit_id}/followups
#                             (nested create only)
#
# A follow-up is created under a visit; patient_id / visit_id are
# taken from that visit. Listing, retrieval, status changes, and
# deletion all live under /api/v1/followups — mirrors the Phase 9
# visit_prescriptions_router pattern, keeping visits.py untouched.
#
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
# ================================================================

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import FollowupStatus
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.user import User
from app.schemas.followup import (
    FollowupCreate,
    FollowupListResponse,
    FollowupResponse,
    FollowupUpdate,
)
from app.services import followup as followup_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/followups", tags=["Followups"])

visit_followups_router = APIRouter(prefix="/api/v1/visits", tags=["Followups"])


# ----------------------------------------------------------------
# CREATE — nested under a visit
# ----------------------------------------------------------------

@visit_followups_router.post(
    "/{visit_id}/followups",
    response_model=FollowupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_followup(
    visit_id: uuid.UUID,
    payload: FollowupCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Schedule a follow-up during/after a visit. Opens as 'pending'."""
    return await followup_service.create_followup(
        db, hospital_id, visit_id, payload
    )


# ----------------------------------------------------------------
# LIST / GET / UPDATE / DELETE
# ----------------------------------------------------------------

@router.get("", response_model=FollowupListResponse)
async def list_followups(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    patient_id: Optional[uuid.UUID] = Query(default=None),
    doctor_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[FollowupStatus] = Query(default=None),
    from_date: Optional[date] = Query(
        default=None, description="Lower bound on recommended_date (inclusive)"
    ),
    to_date: Optional[date] = Query(
        default=None, description="Upper bound on recommended_date (inclusive)"
    ),
):
    """
    Paginated follow-up list, ordered by recommended_date ascending.
    Follow-ups whose parent visit was soft-deleted are still listed.
    """
    return await followup_service.list_followups(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=status.value if status else None,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{followup_id}", response_model=FollowupResponse)
async def get_followup(
    followup_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await followup_service.get_followup(db, hospital_id, followup_id)


@router.patch("/{followup_id}", response_model=FollowupResponse)
async def update_followup(
    followup_id: uuid.UUID,
    payload: FollowupUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Update date/notes or transition status (validated state machine)."""
    return await followup_service.update_followup(
        db, hospital_id, followup_id, payload
    )


@router.delete("/{followup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_followup(
    followup_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Hard-delete a follow-up."""
    await followup_service.delete_followup(db, hospital_id, followup_id)

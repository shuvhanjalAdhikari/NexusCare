# ================================================================
# NexusCare — app/routers/referrals.py
# Referral listing + lifecycle. Referrals are created under
# POST /api/v1/visits/{visit_id}/referrals (see routers/visits.py);
# this router owns the cross-visit list and the state transitions.
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
#
# Authorization: v1 grants referral access to all hospital members.
# Role-based restrictions are a v2 enhancement.
# ================================================================

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import ReferralStatus
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.user import User
from app.schemas.referral import (
    ReferralListResponse,
    ReferralResponse,
    ReferralUpdate,
)
from app.services import referral as referral_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/referrals", tags=["Referrals"])


@router.get("", response_model=ReferralListResponse)
async def list_referrals(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    from_doctor_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by referring doctor (outgoing view)"
    ),
    to_doctor_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by referred-to doctor (incoming view)"
    ),
    referral_status: Optional[ReferralStatus] = Query(
        default=None, alias="status", description="Filter by referral status"
    ),
    from_date: Optional[datetime] = Query(
        default=None, description="Include referrals created at or after this instant"
    ),
    to_date: Optional[datetime] = Query(
        default=None, description="Include referrals created at or before this instant"
    ),
):
    """Paginated referral list, ordered by created_at descending.
    Referrals whose parent visit is soft-deleted are excluded."""
    return await referral_service.list_referrals(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        from_doctor_id=from_doctor_id,
        to_doctor_id=to_doctor_id,
        status=referral_status.value if referral_status else None,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{referral_id}", response_model=ReferralResponse)
async def get_referral(
    referral_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one referral. Orphaned referrals (parent visit soft-deleted)
    surface as NotFoundError."""
    return await referral_service.get_referral(db, hospital_id, referral_id)


@router.patch("/{referral_id}", response_model=ReferralResponse)
async def update_referral(
    referral_id: uuid.UUID,
    payload: ReferralUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Partial update — status (state-machine checked), urgency, notes."""
    return await referral_service.update_referral(
        db, hospital_id, referral_id, payload
    )

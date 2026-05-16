# ================================================================
# NexusCare — app/routers/queue.py
# OPD queue management. Every route runs under get_current_user +
# get_hospital_id; cross-tenant access surfaces as NotFoundError
# (CLAUDE.md §13).
#
# Authorization: any authenticated member of the hospital may manage
# the queue (reception checks patients in, nursing calls them) —
# mirrors the patient and appointment modules.
# ================================================================

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import QueueStatus
from app.database import get_db
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id, get_hospital_timezone
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.queue import QueueAddRequest, QueueResponse, QueueUpdate
from app.services import queue as queue_service


router = APIRouter(prefix="/api/v1/queue", tags=["OPD Queue"])


# ----------------------------------------------------------------
# QUEUE MANAGEMENT
# ----------------------------------------------------------------

@router.post(
    "",
    response_model=QueueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_to_queue(
    payload: QueueAddRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
):
    """Add a patient to the OPD queue — either a walk-in (patient_id +
    doctor_id) or an appointment check-in (appointment_id)."""
    return await queue_service.add_to_queue(
        db,
        hospital_id,
        payload,
        current_user_id=current_user.id,
        membership_id=membership.id,
        tz_name=tz_name,
    )


@router.get("", response_model=list[QueueResponse])
async def list_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
    doctor_id: Optional[uuid.UUID] = Query(default=None, description="Filter by doctor"),
    queue_status: Optional[QueueStatus] = Query(
        default=None, alias="status", description="Filter by queue status"
    ),
):
    """Today's queue (hospital local day), ordered by queue_number."""
    return await queue_service.list_queue(
        db,
        hospital_id,
        tz_name,
        doctor_id=doctor_id,
        status=queue_status.value if queue_status else None,
    )


@router.get("/next", response_model=Optional[QueueResponse])
async def get_next_waiting(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    tz_name: Annotated[str, Depends(get_hospital_timezone)],
    doctor_id: Annotated[uuid.UUID, Query(description="Doctor whose queue to read")],
):
    """The doctor's next waiting patient (lowest queue_number with
    status='waiting'), or null when the waiting queue is empty."""
    return await queue_service.get_next_waiting(db, hospital_id, doctor_id, tz_name)


@router.patch("/{queue_id}", response_model=QueueResponse)
async def update_queue_entry(
    queue_id: uuid.UUID,
    payload: QueueUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Advance a queue entry — call, start consultation, complete, or
    skip. in_consultation / completed transitions sync the linked
    appointment."""
    return await queue_service.update_queue_entry(
        db,
        hospital_id,
        queue_id,
        payload,
        current_user_id=current_user.id,
        membership_id=membership.id,
    )

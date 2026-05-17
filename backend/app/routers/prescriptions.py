# ================================================================
# NexusCare — app/routers/prescriptions.py
# Prescription listing, retrieval, lifecycle, and dispensing. Two
# routers are exported:
#   * router                    — /api/v1/prescriptions
#   * visit_prescriptions_router — /api/v1/visits/{visit_id}/prescriptions
#                                  (nested create only)
#
# A prescription is created under a visit; patient_id / doctor_id are
# taken from that visit. Listing, retrieval, status changes, and
# dispensing all live under /api/v1/prescriptions.
#
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
#
# Authorization: v1 grants prescription access to all hospital
# members. Role-based restrictions are a v2 enhancement.
# ================================================================

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import PrescriptionStatus
from app.database import get_db
from app.dependencies.audit import get_request_metadata
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.audit import RequestMetadata
from app.schemas.prescription import (
    DispenseRequest,
    DispenseResultResponse,
    PrescriptionCreate,
    PrescriptionDetailResponse,
    PrescriptionListResponse,
    PrescriptionResponse,
    PrescriptionUpdate,
)
from app.services import dispense as dispense_service
from app.services import prescription as prescription_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/prescriptions", tags=["Prescriptions"])
visit_prescriptions_router = APIRouter(
    prefix="/api/v1/visits", tags=["Prescriptions"]
)


# ----------------------------------------------------------------
# CREATE — nested under a visit
# ----------------------------------------------------------------

@visit_prescriptions_router.post(
    "/{visit_id}/prescriptions",
    response_model=PrescriptionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prescription(
    visit_id: uuid.UUID,
    payload: PrescriptionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Create a prescription with its items during a visit. The
    prescription opens in status 'draft'; patient_id / doctor_id are
    taken from the visit."""
    return await prescription_service.create_prescription(
        db,
        hospital_id,
        visit_id,
        payload,
        created_by=current_user.id,
        created_by_membership_id=membership.id,
    )


# ----------------------------------------------------------------
# PRESCRIPTION READ
# ----------------------------------------------------------------

@router.get("", response_model=PrescriptionListResponse)
async def list_prescriptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    visit_id: Optional[uuid.UUID] = Query(default=None, description="Filter by visit"),
    patient_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by patient"
    ),
    doctor_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by doctor"
    ),
    prescription_status: Optional[PrescriptionStatus] = Query(
        default=None, alias="status", description="Filter by prescription status"
    ),
):
    """Paginated prescription list, ordered by created_at descending."""
    return await prescription_service.list_prescriptions(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        visit_id=visit_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=prescription_status.value if prescription_status else None,
    )


@router.get("/{prescription_id}", response_model=PrescriptionDetailResponse)
async def get_prescription(
    prescription_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one prescription with its items, each carrying derived
    dispensing progress and full dispense history."""
    return await prescription_service.get_prescription(
        db, hospital_id, prescription_id
    )


# ----------------------------------------------------------------
# PRESCRIPTION UPDATE — state machine
# ----------------------------------------------------------------

@router.patch("/{prescription_id}", response_model=PrescriptionResponse)
async def update_prescription(
    prescription_id: uuid.UUID,
    payload: PrescriptionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    request_meta: Annotated[RequestMetadata, Depends(get_request_metadata)],
):
    """Partial update — notes and/or status (state-machine checked).
    status='dispensed' is rejected; it is set automatically once every
    item is fully dispensed."""
    return await prescription_service.update_prescription(
        db,
        hospital_id,
        prescription_id,
        payload,
        updated_by=current_user.id,
        updated_by_membership_id=membership.id,
        request_meta=request_meta,
    )


# ----------------------------------------------------------------
# DISPENSING
# ----------------------------------------------------------------

@router.post(
    "/{prescription_id}/items/{item_id}/dispense",
    response_model=DispenseResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def dispense_item(
    prescription_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: DispenseRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    request_meta: Annotated[RequestMetadata, Depends(get_request_metadata)],
):
    """Dispense a quantity of one prescription item against a drug
    batch. The prescription must be 'issued'. Stock is drawn from a
    single batch (FIFO auto-selection, or an explicit batch_id)."""
    return await dispense_service.dispense_item(
        db,
        hospital_id,
        prescription_id,
        item_id,
        payload,
        dispensed_by=current_user.id,
        dispensed_by_membership_id=membership.id,
        request_meta=request_meta,
    )

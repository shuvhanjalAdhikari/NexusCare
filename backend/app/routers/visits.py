# ================================================================
# NexusCare — app/routers/visits.py
# Clinical visit CRUD + nested vitals / diagnoses sub-resources, plus
# the create-referral-during-a-visit route. Every route runs under
# get_current_user + get_hospital_id; cross-tenant access surfaces as
# NotFoundError (CLAUDE.md §13).
#
# Authorization: v1 grants visit/referral access to all hospital
# members. Role-based restrictions (e.g. clinical-only for vitals) is
# a v2 enhancement.
# ================================================================

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import VisitStatus
from app.database import get_db
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.referral import ReferralCreate, ReferralResponse
from app.schemas.visit import (
    DiagnosisCreate,
    DiagnosisResponse,
    DiagnosisUpdate,
    VisitCreate,
    VisitDetailResponse,
    VisitListResponse,
    VisitResponse,
    VisitUpdate,
    VitalCreate,
    VitalResponse,
    VitalUpdate,
)
from app.services import referral as referral_service
from app.services import visit as visit_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/visits", tags=["Visits"])


# ----------------------------------------------------------------
# VISIT CRUD
# ----------------------------------------------------------------

@router.post("", response_model=VisitResponse, status_code=status.HTTP_201_CREATED)
async def create_visit(
    payload: VisitCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Start a clinical visit. The visit opens in status 'waiting'."""
    return await visit_service.create_visit(
        db,
        hospital_id,
        payload,
        created_by=current_user.id,
        created_by_membership_id=membership.id,
    )


@router.get("", response_model=VisitListResponse)
async def list_visits(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    patient_id: Optional[uuid.UUID] = Query(default=None, description="Filter by patient"),
    doctor_id: Optional[uuid.UUID] = Query(default=None, description="Filter by doctor"),
    visit_status: Optional[VisitStatus] = Query(
        default=None, alias="status", description="Filter by visit status"
    ),
    from_date: Optional[datetime] = Query(
        default=None, description="Include visits created at or after this instant"
    ),
    to_date: Optional[datetime] = Query(
        default=None, description="Include visits created at or before this instant"
    ),
):
    """Paginated visit list, ordered by created_at descending."""
    return await visit_service.list_visits(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=visit_status.value if visit_status else None,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/{visit_id}", response_model=VisitDetailResponse)
async def get_visit(
    visit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one visit with its nested vitals, diagnoses and referrals."""
    return await visit_service.get_visit(db, hospital_id, visit_id)


@router.patch("/{visit_id}", response_model=VisitResponse)
async def update_visit(
    visit_id: uuid.UUID,
    payload: VisitUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Partial update of SOAP notes and/or status (state-machine checked)."""
    return await visit_service.update_visit(
        db,
        hospital_id,
        visit_id,
        payload,
        updated_by=current_user.id,
        updated_by_membership_id=membership.id,
    )


@router.delete("/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visit(
    visit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Soft-delete a visit — stamps deleted_at."""
    await visit_service.soft_delete_visit(db, hospital_id, visit_id)


# ----------------------------------------------------------------
# VITALS (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{visit_id}/vitals",
    response_model=VitalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_vital(
    visit_id: uuid.UUID,
    payload: VitalCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Record a vitals snapshot. BMI is computed when weight + height
    are both supplied."""
    return await visit_service.add_vital(
        db,
        hospital_id,
        visit_id,
        payload,
        recorded_by=current_user.id,
        recorded_by_membership_id=membership.id,
    )


@router.get("/{visit_id}/vitals", response_model=list[VitalResponse])
async def list_vitals(
    visit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """List this visit's vitals in recorded_at order."""
    return await visit_service.list_vitals(db, hospital_id, visit_id)


@router.patch("/{visit_id}/vitals/{vital_id}", response_model=VitalResponse)
async def update_vital(
    visit_id: uuid.UUID,
    vital_id: uuid.UUID,
    payload: VitalUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Correct a vitals reading. BMI is recomputed from merged values."""
    return await visit_service.update_vital(
        db, hospital_id, visit_id, vital_id, payload
    )


@router.delete(
    "/{visit_id}/vitals/{vital_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_vital(
    visit_id: uuid.UUID,
    vital_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Hard-delete a vitals reading."""
    await visit_service.delete_vital(db, hospital_id, visit_id, vital_id)


# ----------------------------------------------------------------
# DIAGNOSES (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{visit_id}/diagnoses",
    response_model=DiagnosisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_diagnosis(
    visit_id: uuid.UUID,
    payload: DiagnosisCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Record a diagnosis on a visit."""
    return await visit_service.add_diagnosis(db, hospital_id, visit_id, payload)


@router.get("/{visit_id}/diagnoses", response_model=list[DiagnosisResponse])
async def list_diagnoses(
    visit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """List this visit's diagnoses in created_at order."""
    return await visit_service.list_diagnoses(db, hospital_id, visit_id)


@router.patch(
    "/{visit_id}/diagnoses/{diagnosis_id}",
    response_model=DiagnosisResponse,
)
async def update_diagnosis(
    visit_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    payload: DiagnosisUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Partial update of a diagnosis."""
    return await visit_service.update_diagnosis(
        db, hospital_id, visit_id, diagnosis_id, payload
    )


@router.delete(
    "/{visit_id}/diagnoses/{diagnosis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_diagnosis(
    visit_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Hard-delete a diagnosis."""
    await visit_service.delete_diagnosis(db, hospital_id, visit_id, diagnosis_id)


# ----------------------------------------------------------------
# REFERRALS (created during a visit)
# ----------------------------------------------------------------

@router.post(
    "/{visit_id}/referrals",
    response_model=ReferralResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_referral(
    visit_id: uuid.UUID,
    payload: ReferralCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Create a referral during a visit. from_doctor_id is taken from
    the visit's doctor. Listing and lifecycle live under
    /api/v1/referrals."""
    return await referral_service.create_referral(
        db, hospital_id, visit_id, payload
    )

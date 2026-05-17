# ================================================================
# NexusCare — app/routers/patients.py
# Patient CRUD + nested allergy sub-resource. Every route runs under
# get_current_user + get_hospital_id; cross-tenant access surfaces as
# NotFoundError (CLAUDE.md §13).
# ================================================================

import uuid
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Gender
from app.database import get_db
from app.dependencies.audit import get_request_metadata
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.audit import RequestMetadata
from app.schemas.patient import (
    AllergyCreate,
    AllergyResponse,
    AllergyUpdate,
    PatientCreate,
    PatientListResponse,
    PatientResponse,
    PatientUpdate,
)
from app.services import patient as patient_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/patients", tags=["Patients"])


# ----------------------------------------------------------------
# PATIENT CRUD
# ----------------------------------------------------------------

@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient(
    payload: PatientCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await patient_service.create_patient(db, hospital_id, payload)


@router.get("", response_model=PatientListResponse)
async def list_patients(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    q: Optional[str] = Query(
        default=None,
        max_length=200,
        description="Substring match on first_name, last_name, phone, patient_number (case-insensitive)",
    ),
    gender: Optional[Gender] = Query(default=None, description="Filter by gender"),
    blood_group: Optional[str] = Query(
        default=None, max_length=10, description="Exact match on blood_group"
    ),
    include_inactive: bool = Query(
        default=False,
        description="When true, include is_active=false patients. Soft-deleted patients are never returned.",
    ),
    sort: Literal["recent", "name"] = Query(
        default="recent",
        description="Default 'recent' orders by created_at DESC; 'name' orders alphabetically by first_name, last_name.",
    ),
):
    """
    Paginated patient list with search and filters.

    Default ordering is `created_at DESC` so receptionists see
    recently-registered patients first — alpha order would bury the
    patient who just walked in. Pass `?sort=name` to switch to
    alphabetical order.

    By default the list excludes suspended (`is_active=false`)
    patients; pass `?include_inactive=true` to include them.
    Soft-deleted patients are never returned regardless of this flag.
    """
    return await patient_service.list_patients(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        q=q,
        gender=gender.value if gender else None,
        blood_group=blood_group,
        include_inactive=include_inactive,
        sort=sort,
    )


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await patient_service.get_patient(db, hospital_id, patient_id)


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await patient_service.update_patient(db, hospital_id, patient_id, payload)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    request_meta: Annotated[RequestMetadata, Depends(get_request_metadata)],
):
    await patient_service.soft_delete_patient(
        db,
        hospital_id,
        patient_id,
        acting_user_id=current_user.id,
        acting_membership_id=membership.id,
        request_meta=request_meta,
    )


# ----------------------------------------------------------------
# ALLERGIES (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{patient_id}/allergies",
    response_model=AllergyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_allergy(
    patient_id: uuid.UUID,
    payload: AllergyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await patient_service.add_allergy(db, hospital_id, patient_id, payload)


@router.get("/{patient_id}/allergies", response_model=list[AllergyResponse])
async def list_allergies(
    patient_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await patient_service.list_allergies(db, hospital_id, patient_id)


@router.patch(
    "/{patient_id}/allergies/{allergy_id}",
    response_model=AllergyResponse,
)
async def update_allergy(
    patient_id: uuid.UUID,
    allergy_id: uuid.UUID,
    payload: AllergyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    return await patient_service.update_allergy(
        db, hospital_id, patient_id, allergy_id, payload
    )


@router.delete(
    "/{patient_id}/allergies/{allergy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_allergy(
    patient_id: uuid.UUID,
    allergy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    await patient_service.delete_allergy(db, hospital_id, patient_id, allergy_id)

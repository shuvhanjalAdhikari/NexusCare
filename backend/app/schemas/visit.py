# ================================================================
# NexusCare — app/schemas/visit.py
# Pydantic v2 schemas for the clinical visit module:
#   * Visit CRUD + listing
#   * Vitals  (sub-resource of a visit)
#   * Diagnoses (sub-resource of a visit)
#
# hospital_id and the audit columns (created_by / updated_by /
# recorded_by and their membership ids) are NEVER accepted from the
# request body — hospital_id comes from the JWT, the audit ids come
# from the auth context.
#
# BMI is computed server-side from weight_kg + height_cm whenever both
# are present (POST and PATCH); any client-supplied bmi is overwritten
# in that case. See services/visit.py.
# ================================================================

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import DiagnosisType, VisitStatus
from app.schemas.referral import ReferralResponse


# ----------------------------------------------------------------
# VITALS
# ----------------------------------------------------------------

class VitalBase(BaseModel):
    """Shared vitals fields. Every measurement is optional — a reading
    may capture only a subset (e.g. BP alone)."""

    bp_systolic: Optional[int] = Field(default=None, ge=0, le=400)
    bp_diastolic: Optional[int] = Field(default=None, ge=0, le=300)
    heart_rate: Optional[int] = Field(default=None, ge=0, le=400)
    temperature: Optional[Decimal] = None
    spo2: Optional[int] = Field(default=None, ge=0, le=100)
    weight_kg: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    bmi: Optional[Decimal] = None
    triage_level: Optional[int] = Field(default=None, ge=1, le=5)


class VitalCreate(VitalBase):
    """Body for POST /api/v1/visits/{visit_id}/vitals."""


class VitalUpdate(VitalBase):
    """Body for PATCH /api/v1/visits/{visit_id}/vitals/{vital_id}.
    All fields optional — corrects an individual reading."""


class VitalResponse(VitalBase):
    """Flat vitals shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    visit_id: UUID
    hospital_id: UUID
    recorded_by: Optional[UUID] = None
    recorded_by_membership_id: Optional[UUID] = None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# DIAGNOSES
# ----------------------------------------------------------------

class DiagnosisBase(BaseModel):
    """Shared diagnosis fields."""

    icd_code: Optional[str] = None
    diagnosis_text: str
    diagnosis_type: DiagnosisType = DiagnosisType.PRIMARY
    is_chronic: bool = False


class DiagnosisCreate(DiagnosisBase):
    """Body for POST /api/v1/visits/{visit_id}/diagnoses."""


class DiagnosisUpdate(BaseModel):
    """Body for PATCH /api/v1/visits/{visit_id}/diagnoses/{id}.
    All fields optional."""

    icd_code: Optional[str] = None
    diagnosis_text: Optional[str] = None
    diagnosis_type: Optional[DiagnosisType] = None
    is_chronic: Optional[bool] = None


class DiagnosisResponse(DiagnosisBase):
    """Flat diagnosis shape — serialized directly from the ORM row.
    diagnosis_type reads the model's diagnosis_type attribute (the DB
    column is named 'type')."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    visit_id: UUID
    hospital_id: UUID
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# VISIT
# ----------------------------------------------------------------

class VisitBase(BaseModel):
    """Shared visit fields between create and the flat response."""

    patient_id: UUID
    doctor_id: UUID
    appointment_id: Optional[UUID] = None
    queue_id: Optional[UUID] = None
    chief_complaint: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    examination_notes: Optional[str] = None
    assessment_notes: Optional[str] = None
    plan_notes: Optional[str] = None


class VisitCreate(VisitBase):
    """Body for POST /api/v1/visits.

    A new visit always starts in status 'waiting'. appointment_id /
    queue_id are optional — walk-in visits have neither; when supplied
    the service verifies they reference the same patient + doctor."""


class VisitUpdate(BaseModel):
    """Body for PATCH /api/v1/visits/{id}. All fields optional.

    status transitions are validated against the visit state machine
    in the service layer."""

    status: Optional[VisitStatus] = None
    chief_complaint: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    examination_notes: Optional[str] = None
    assessment_notes: Optional[str] = None
    plan_notes: Optional[str] = None


class VisitResponse(VisitBase):
    """Flat visit shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    status: VisitStatus
    created_by: Optional[UUID] = None
    created_by_membership_id: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    updated_by_membership_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class VisitDetailResponse(VisitResponse):
    """Visit with its nested vitals, diagnoses and referrals. Returned
    by GET /api/v1/visits/{id}; the service eager-loads all three."""

    vitals: list[VitalResponse] = []
    diagnoses: list[DiagnosisResponse] = []
    referrals: list[ReferralResponse] = []


class VisitListItem(BaseModel):
    """Lean visit shape for the paginated list — omits the SOAP body
    and audit columns."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    patient_id: UUID
    doctor_id: UUID
    status: VisitStatus
    chief_complaint: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

VisitListResponse = PagedResponse[VisitListItem]

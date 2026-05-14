# ================================================================
# NexusCare — app/schemas/patient.py
# Pydantic v2 schemas for the patient module:
#   * Patient CRUD + listing
#   * Nested allergy CRUD
# hospital_id and patient_number are NEVER accepted from the body —
# hospital_id comes from the JWT, patient_number is server-generated
# at registration and is immutable thereafter.
# ================================================================

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constants.enums import AllergySeverity, Gender
from app.utils.email import normalize_email
from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# ALLERGY SCHEMAS
# ----------------------------------------------------------------

class AllergyBase(BaseModel):
    """Shared allergy fields. Both severity and reaction are optional per schema."""

    allergen: str = Field(min_length=1, max_length=200)
    severity: Optional[AllergySeverity] = None
    reaction: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None


class AllergyCreate(AllergyBase):
    """Body for POST /api/v1/patients/{patient_id}/allergies."""


class AllergyUpdate(BaseModel):
    """Body for PATCH /api/v1/patients/{patient_id}/allergies/{allergy_id}.
    All fields optional; unset fields are left untouched."""

    allergen: Optional[str] = Field(default=None, min_length=1, max_length=200)
    severity: Optional[AllergySeverity] = None
    reaction: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None


class AllergyResponse(AllergyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    hospital_id: UUID
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# PATIENT SCHEMAS
# ----------------------------------------------------------------

class PatientBase(BaseModel):
    """Shared patient fields. All optional except first_name/last_name."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[Gender] = None
    blood_group: Optional[str] = Field(default=None, max_length=10)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[EmailStr] = Field(default=None, max_length=150)
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(default=None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=30)
    emergency_contact_relationship: Optional[str] = Field(default=None, max_length=80)
    insurance_provider: Optional[str] = Field(default=None, max_length=150)
    insurance_policy_number: Optional[str] = Field(default=None, max_length=100)

    @field_validator("dob")
    @classmethod
    def _dob_not_future(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("dob cannot be in the future")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v):
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def _trim_phone(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class PatientCreate(PatientBase):
    """Body for POST /api/v1/patients. patient_number is server-generated."""


class PatientUpdate(BaseModel):
    """Body for PATCH /api/v1/patients/{patient_id}. All fields optional.
    patient_number is deliberately absent — it is identity, immutable after
    registration."""

    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[Gender] = None
    blood_group: Optional[str] = Field(default=None, max_length=10)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[EmailStr] = Field(default=None, max_length=150)
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(default=None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=30)
    emergency_contact_relationship: Optional[str] = Field(default=None, max_length=80)
    insurance_provider: Optional[str] = Field(default=None, max_length=150)
    insurance_policy_number: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("dob")
    @classmethod
    def _dob_not_future(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("dob cannot be in the future")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v):
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("phone", "emergency_contact_phone", mode="before")
    @classmethod
    def _trim_phone(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class PatientResponse(PatientBase):
    """Full patient detail, including nested allergies (eagerly loaded)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    patient_number: str
    is_active: bool
    allergies: list[AllergyResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PatientListItem(BaseModel):
    """Lean row for list/search endpoints — no allergies, no insurance, no
    emergency contact. Designed for quick reception-desk lookups."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_number: str
    first_name: str
    last_name: str
    dob: Optional[date] = None
    gender: Optional[Gender] = None
    blood_group: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    created_at: datetime


PatientListResponse = PagedResponse[PatientListItem]

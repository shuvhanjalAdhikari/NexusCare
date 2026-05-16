# ================================================================
# NexusCare — app/schemas/prescription.py
# Pydantic v2 schemas for the prescription + dispensing module:
#   * Prescription create / update / listing
#   * Prescription items (created together with the prescription)
#   * Dispense request + result + dispense-log
#
# hospital_id and the audit columns are NEVER accepted from the
# request body. patient_id / doctor_id are NOT accepted either — they
# are derived from the parent visit.
#
# dispensed_quantity / remaining_quantity / is_fully_dispensed are
# DERIVED — there is no stored counter on prescription_items. The
# service computes them from SUM(dispense_logs.quantity_dispensed).
# ================================================================

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import PrescriptionStatus


# ----------------------------------------------------------------
# PRESCRIPTION ITEM
# ----------------------------------------------------------------

class PrescriptionItemCreate(BaseModel):
    """One drug line supplied when creating a prescription. quantity is
    the prescribed amount and is required (the DB column is nullable,
    but a line with no quantity cannot be dispensed)."""

    drug_id: UUID
    quantity: int = Field(ge=1)
    dose: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    duration_days: Optional[int] = Field(default=None, ge=1)
    instructions: Optional[str] = None


class DispenseLogResponse(BaseModel):
    """An immutable dispense event — serialized from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    prescription_item_id: UUID
    batch_id: UUID
    quantity_dispensed: int
    dispensed_by: UUID
    dispensed_by_membership_id: Optional[UUID] = None
    dispensed_at: datetime
    notes: Optional[str] = None


class PrescriptionItemResponse(BaseModel):
    """A prescription item with its derived dispensing progress and
    full dispense history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prescription_id: UUID
    hospital_id: UUID
    drug_id: UUID
    dose: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    duration_days: Optional[int] = None
    instructions: Optional[str] = None
    quantity: Optional[int] = None
    dispensed_quantity: int
    remaining_quantity: int
    is_fully_dispensed: bool
    created_at: datetime
    updated_at: datetime
    dispense_logs: list[DispenseLogResponse] = []


# ----------------------------------------------------------------
# PRESCRIPTION
# ----------------------------------------------------------------

class PrescriptionCreate(BaseModel):
    """Body for POST /api/v1/visits/{visit_id}/prescriptions. The
    prescription opens in status 'draft'. patient_id / doctor_id are
    taken from the visit."""

    notes: Optional[str] = None
    items: list[PrescriptionItemCreate] = Field(min_length=1)


class PrescriptionUpdate(BaseModel):
    """Body for PATCH /api/v1/prescriptions/{id}. All fields optional.

    status may be moved to 'issued' or 'cancelled'; 'dispensed' is set
    automatically when every item is fully dispensed and cannot be set
    via PATCH."""

    notes: Optional[str] = None
    status: Optional[PrescriptionStatus] = None


class PrescriptionResponse(BaseModel):
    """Flat prescription shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    visit_id: UUID
    patient_id: UUID
    doctor_id: UUID
    status: PrescriptionStatus
    notes: Optional[str] = None
    created_by: Optional[UUID] = None
    created_by_membership_id: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    updated_by_membership_id: Optional[UUID] = None
    issued_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PrescriptionDetailResponse(PrescriptionResponse):
    """Prescription with its items (each carrying derived dispensing
    progress + dispense history). Returned by GET /prescriptions/{id}
    and the create endpoint."""

    items: list[PrescriptionItemResponse] = []


# ----------------------------------------------------------------
# DISPENSING
# ----------------------------------------------------------------

class DispenseRequest(BaseModel):
    """Body for POST /prescriptions/{id}/items/{item_id}/dispense.

    batch_id is optional — when omitted the service FIFO-selects the
    non-expired batch with the earliest expiry that can fulfil the
    whole quantity from a single batch."""

    quantity: int = Field(ge=1)
    batch_id: Optional[UUID] = None
    notes: Optional[str] = None


class DispenseResultResponse(BaseModel):
    """Outcome of a single dispense event."""

    dispense_log_id: UUID
    dispense_log: DispenseLogResponse
    batch_remaining_stock: int
    item_dispensed_quantity: int
    item_remaining_quantity: int
    item_fully_dispensed: bool
    prescription_status: PrescriptionStatus


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

PrescriptionListResponse = PagedResponse[PrescriptionResponse]

# ================================================================
# NexusCare — app/schemas/lab.py
# Pydantic v2 schemas for the diagnostic lab module:
#   * Lab test catalogue (per-hospital reference data)
#   * Lab orders (a doctor's request raised during a visit)
#   * Lab results (one-to-one with an order — UNIQUE lab_order_id)
#
# hospital_id and all audit columns are NEVER accepted from the
# request body. patient_id / doctor_id are NOT accepted either — they
# are derived from the parent visit.
#
# test_name / has_result on LabOrderResponse are DERIVED — the service
# attaches them to the ORM instance before serialization.
# ================================================================

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import LabOrderStatus, LabPriority


# ----------------------------------------------------------------
# LAB TEST CATALOGUE
# ----------------------------------------------------------------

class LabTestBase(BaseModel):
    """Shared lab-test catalogue fields."""

    name: str = Field(min_length=1, max_length=150)
    category: Optional[str] = Field(default=None, max_length=100)
    sample_type: Optional[str] = Field(default=None, max_length=80)
    tat_hours: Optional[int] = Field(default=None, ge=0)
    reference_range: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=40)
    price: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)


class LabTestCreate(LabTestBase):
    """Body for POST /api/v1/lab-tests."""

    pass


class LabTestUpdate(BaseModel):
    """Body for PATCH /api/v1/lab-tests/{id}. All fields optional.

    is_active=false deactivates the catalogue entry — lab tests are
    never deleted, to preserve referential integrity with historical
    lab orders that reference them."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    category: Optional[str] = Field(default=None, max_length=100)
    sample_type: Optional[str] = Field(default=None, max_length=80)
    tat_hours: Optional[int] = Field(default=None, ge=0)
    reference_range: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=40)
    price: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    is_active: Optional[bool] = None


class LabTestResponse(LabTestBase):
    """A lab-test catalogue entry — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# LAB RESULT
# ----------------------------------------------------------------

class LabResultCreate(BaseModel):
    """Body for POST /api/v1/lab-orders/{order_id}/result.

    is_abnormal is client-supplied (the lab tech compares value to the
    reference range). file_url is a plain string — the frontend uploads
    the result document elsewhere and POSTs the resulting URL here."""

    result_value: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=40)
    reference_range: Optional[str] = None
    is_abnormal: bool = False
    file_url: Optional[str] = None
    notes: Optional[str] = None


class LabResultUpdate(BaseModel):
    """Body for PATCH /api/v1/lab-orders/{order_id}/result. All fields
    optional — used to correct a result before the doctor reviews it.

    uploaded_by is NOT accepted: a correction keeps the original lab
    technician on record."""

    result_value: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=40)
    reference_range: Optional[str] = None
    is_abnormal: Optional[bool] = None
    file_url: Optional[str] = None
    notes: Optional[str] = None


class LabResultResponse(BaseModel):
    """A lab result — one-to-one with its order. Serialized from the ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_order_id: UUID
    hospital_id: UUID
    result_value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    is_abnormal: bool
    file_url: Optional[str] = None
    notes: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    uploaded_by_membership_id: Optional[UUID] = None
    reviewed_by: Optional[UUID] = None
    reviewed_by_membership_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# LAB ORDER
# ----------------------------------------------------------------

class LabOrderCreate(BaseModel):
    """Body for POST /api/v1/visits/{visit_id}/lab-orders. The order
    opens in status 'ordered'. patient_id / doctor_id are taken from
    the visit; test_id references an active lab-test catalogue entry."""

    test_id: UUID
    priority: LabPriority = LabPriority.ROUTINE


class LabOrderUpdate(BaseModel):
    """Body for PATCH /api/v1/lab-orders/{id}. status is moved along the
    lab-order state machine; no other field is mutable on an order."""

    status: Optional[LabOrderStatus] = None


class LabOrderResponse(BaseModel):
    """Flat lab-order shape — used in list views. test_name and
    has_result are derived fields attached by the service."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    visit_id: UUID
    patient_id: UUID
    doctor_id: UUID
    test_id: UUID
    test_name: str
    priority: LabPriority
    status: LabOrderStatus
    has_result: bool
    sample_collected_at: Optional[datetime] = None
    result_ready_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    created_by_membership_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class LabOrderDetailResponse(LabOrderResponse):
    """Lab order with its nested test catalogue entry and its result
    (None until a lab technician records one). Returned by
    GET /lab-orders/{id} and the create endpoint."""

    test: LabTestResponse
    result: Optional[LabResultResponse] = None


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

LabOrderListResponse = PagedResponse[LabOrderResponse]

# ================================================================
# NexusCare — app/schemas/invoice.py
# Pydantic v2 schemas for the billing module:
#   * Invoices — dual-mode create (auto-from-visit / manual), update,
#     listing, detail
#   * Invoice items — the line-item sub-resource
#   * Payments — append-only payment events (a refund is a negative
#     amount)
#   * Billing reports — revenue summary
#
# hospital_id and all audit columns are NEVER accepted from the request
# body. In auto-from-visit mode patient_id is derived from the visit.
#
# Money: every amount is a decimal.Decimal. The service quantizes to
# 2dp ROUND_HALF_UP at storage time. amount_paid / balance_due on the
# invoice responses are DERIVED — the service computes them from the
# invoice's payments and attaches them before serialization.
# ================================================================

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants.enums import InvoiceStatus, PaymentMethod


# ----------------------------------------------------------------
# INVOICE ITEM
# ----------------------------------------------------------------

class InvoiceItemCreate(BaseModel):
    """One manual line item. total_price is computed server-side as
    quantity * unit_price — never accepted from the body."""

    description: str = Field(min_length=1, max_length=300)
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(ge=0)
    service_id: Optional[UUID] = None


class InvoiceItemUpdate(BaseModel):
    """Partial update of a line item. Allowed only while the parent
    invoice is still in status 'draft'."""

    description: Optional[str] = Field(default=None, min_length=1, max_length=300)
    quantity: Optional[int] = Field(default=None, ge=1)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    service_id: Optional[UUID] = None


class InvoiceItemResponse(BaseModel):
    """An invoice line item — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    hospital_id: UUID
    service_id: Optional[UUID] = None
    description: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# PAYMENT
# ----------------------------------------------------------------

class PaymentCreate(BaseModel):
    """Body for POST /api/v1/invoices/{id}/payments.

    amount is positive for a payment and negative for a refund — the
    payments table has no CHECK on amount. amount must not be zero
    (validated by the service)."""

    amount: Decimal
    method: PaymentMethod
    reference: Optional[str] = Field(default=None, max_length=200)


class PaymentResponse(BaseModel):
    """A payment event — serialized directly from the ORM row. Payments
    are immutable: there is no updated_at."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    hospital_id: UUID
    amount: Decimal
    method: PaymentMethod
    reference: Optional[str] = None
    recorded_by: Optional[UUID] = None
    recorded_by_membership_id: Optional[UUID] = None
    paid_at: datetime
    created_at: datetime


# ----------------------------------------------------------------
# INVOICE
# ----------------------------------------------------------------

class InvoiceCreate(BaseModel):
    """
    Body for POST /api/v1/invoices. Two mutually-exclusive modes:

    * Auto-from-visit — supply visit_id only. The server aggregates the
      consultation fee, prescription drugs, and lab orders of that visit
      into line items. patient_id is taken from the visit.
    * Manual — supply a non-empty items[] array. patient_id is required
      unless visit_id is also given (then it is derived). visit_id, if
      present, is stored only as a reference link (no aggregation).

    discount_amount / tax_amount are pass-through (the server never
    computes tax); the server computes subtotal and total_amount.
    """

    patient_id: Optional[UUID] = None
    visit_id: Optional[UUID] = None
    items: Optional[list[InvoiceItemCreate]] = None
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    due_date: Optional[date] = None


class InvoiceUpdate(BaseModel):
    """
    Body for PATCH /api/v1/invoices/{id}. status moves along the invoice
    state machine ('partial' / 'paid' are payment-driven and rejected
    here). discount_amount / tax_amount / due_date may be changed only
    while the invoice is still 'draft'.
    """

    status: Optional[InvoiceStatus] = None
    discount_amount: Optional[Decimal] = Field(default=None, ge=0)
    tax_amount: Optional[Decimal] = Field(default=None, ge=0)
    due_date: Optional[date] = None


class InvoiceResponse(BaseModel):
    """Flat invoice shape — used in list views. amount_paid and
    balance_due are derived fields attached by the service."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    patient_id: UUID
    appointment_id: Optional[UUID] = None
    visit_id: Optional[UUID] = None
    status: InvoiceStatus
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    due_date: Optional[date] = None
    paid_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    created_by_membership_id: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    updated_by_membership_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class InvoiceDetailResponse(InvoiceResponse):
    """Invoice with its line items and payment history. Returned by
    GET /invoices/{id} and the create endpoint."""

    items: list[InvoiceItemResponse] = []
    payments: list[PaymentResponse] = []


# ----------------------------------------------------------------
# BILLING REPORTS
# ----------------------------------------------------------------

class RevenueReportResponse(BaseModel):
    """Revenue over a date range, by payments' paid_at.

    gross   — sum of positive payments
    refunds — sum of refunds (negative payments), reported as a positive
    net     — gross - refunds (the true cash position)"""

    from_date: date
    to_date: date
    gross: Decimal
    refunds: Decimal
    net: Decimal
    payment_count: int


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

InvoiceListResponse = PagedResponse[InvoiceResponse]

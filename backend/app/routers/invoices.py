# ================================================================
# NexusCare — app/routers/invoices.py
# Billing routes: invoices, the nested line-item sub-resource, and the
# nested append-only payments sub-resource. All under /api/v1/invoices.
#
# An invoice is created either by aggregating a visit's charges or from
# a manual items[] array. Line items can be changed only while the
# invoice is 'draft'. Payments are append-only — no PATCH, no DELETE;
# a refund is a payment with a negative amount.
#
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
#
# Authorization: v1 grants billing access to all hospital members.
# Role-based restrictions are a v2 enhancement.
# ================================================================

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import InvoiceStatus
from app.database import get_db
from app.dependencies.audit import get_request_metadata
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.audit import RequestMetadata
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceDetailResponse,
    InvoiceItemCreate,
    InvoiceItemUpdate,
    InvoiceListResponse,
    InvoiceUpdate,
    PaymentCreate,
    PaymentResponse,
)
from app.services import invoice as invoice_service
from app.services import payment as payment_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/invoices", tags=["Billing"])


# ----------------------------------------------------------------
# INVOICE — create / read / update / delete
# ----------------------------------------------------------------

@router.post(
    "", response_model=InvoiceDetailResponse, status_code=status.HTTP_201_CREATED
)
async def create_invoice(
    payload: InvoiceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Create an invoice — auto-aggregated from a visit, or from a
    manual items[] array. The invoice opens in status 'draft'."""
    return await invoice_service.create_invoice(
        db,
        hospital_id,
        payload,
        created_by=current_user.id,
        created_by_membership_id=membership.id,
    )


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    patient_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by patient"
    ),
    invoice_status: Optional[InvoiceStatus] = Query(
        default=None, alias="status", description="Filter by invoice status"
    ),
    date_from: Optional[date] = Query(
        default=None, description="Earliest invoice date (inclusive)"
    ),
    date_to: Optional[date] = Query(
        default=None, description="Latest invoice date (inclusive)"
    ),
):
    """Paginated invoice list, ordered by created_at descending.
    Invoices whose linked visit was soft-deleted are excluded."""
    return await invoice_service.list_invoices(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        patient_id=patient_id,
        status=invoice_status.value if invoice_status else None,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one invoice with its line items, payment history, and the
    derived amount_paid / balance_due."""
    return await invoice_service.get_invoice(db, hospital_id, invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceDetailResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Partial update — status (state-machine checked) and, while still
    'draft', discount_amount / tax_amount / due_date."""
    return await invoice_service.update_invoice(
        db,
        hospital_id,
        invoice_id,
        payload,
        updated_by=current_user.id,
        updated_by_membership_id=membership.id,
    )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Soft-delete an invoice — only while still in status 'draft'."""
    await invoice_service.delete_invoice(db, hospital_id, invoice_id)


# ----------------------------------------------------------------
# INVOICE ITEMS — sub-resource, draft only
# ----------------------------------------------------------------

@router.post(
    "/{invoice_id}/items",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_invoice_item(
    invoice_id: uuid.UUID,
    payload: InvoiceItemCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Add a line item to a draft invoice; the invoice totals are
    recomputed and the updated invoice returned."""
    return await invoice_service.add_invoice_item(
        db,
        hospital_id,
        invoice_id,
        payload,
        updated_by=current_user.id,
        updated_by_membership_id=membership.id,
    )


@router.patch(
    "/{invoice_id}/items/{item_id}", response_model=InvoiceDetailResponse
)
async def update_invoice_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: InvoiceItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Update a line item on a draft invoice; totals are recomputed."""
    return await invoice_service.update_invoice_item(
        db,
        hospital_id,
        invoice_id,
        item_id,
        payload,
        updated_by=current_user.id,
        updated_by_membership_id=membership.id,
    )


@router.delete(
    "/{invoice_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_invoice_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Remove a line item from a draft invoice; totals are recomputed."""
    await invoice_service.delete_invoice_item(
        db,
        hospital_id,
        invoice_id,
        item_id,
        updated_by=current_user.id,
        updated_by_membership_id=membership.id,
    )


# ----------------------------------------------------------------
# PAYMENTS — append-only sub-resource
# ----------------------------------------------------------------

@router.post(
    "/{invoice_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    request_meta: Annotated[RequestMetadata, Depends(get_request_metadata)],
):
    """Record a payment (positive amount) or refund (negative amount)
    against an invoice. The invoice status is advanced automatically."""
    return await payment_service.record_payment(
        db,
        hospital_id,
        invoice_id,
        payload,
        recorded_by=current_user.id,
        recorded_by_membership_id=membership.id,
        request_meta=request_meta,
    )


@router.get("/{invoice_id}/payments", response_model=list[PaymentResponse])
async def list_payments(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """List every payment recorded against an invoice, oldest first."""
    return await payment_service.list_payments(db, hospital_id, invoice_id)

# ================================================================
# NexusCare — app/services/invoice.py
# Billing business logic: invoice CRUD, the dual-mode create
# (auto-from-visit aggregation / manual line items), the line-item
# sub-resource, the invoice state machine, and the outstanding report.
# Payment recording lives in services/payment.py.
#
# All queries are hospital-scoped (CLAUDE.md §13).
#
# ----------------------------------------------------------------
# MONEY
# ----------------------------------------------------------------
# Every monetary value is a decimal.Decimal — never float. All amounts
# are quantized to 2 decimal places with ROUND_HALF_UP at storage time
# (the DB columns are NUMERIC(10,2)). A line's total_price is always
# quantity * unit_price; an invoice's subtotal is the sum of its line
# total_prices; total_amount = subtotal - discount_amount + tax_amount.
# Tax is NEVER computed by the server — discount_amount and tax_amount
# are pass-through values supplied by the caller. A discount exceeding
# the subtotal is rejected with BadRequestError.
#
# ----------------------------------------------------------------
# INVOICE STATE MACHINE (CLAUDE.md / 01_schema.sql status CHECK)
# ----------------------------------------------------------------
# The schema allows: draft, unpaid, partial, paid, overdue, void,
# refunded. v1 uses five of them:
#
#   draft   → unpaid (finalize — locks line items) | void
#   unpaid  → partial | paid (PAYMENT-DRIVEN only) ; → void
#   partial → paid           (PAYMENT-DRIVEN only) ; → void
#   paid    → terminal
#   void    → terminal
#
# "unpaid" is the schema's term for the brief's "issued": the invoice
# is finalized and awaiting payment. 'partial' and 'paid' are reached
# ONLY by recording payments (services/payment.py) — a PATCH targeting
# them is rejected, the same way prescriptions reject manual
# 'dispensed'.
#
# TODO (v2): 'overdue' is not auto-driven — flagging an invoice overdue
# when it passes due_date needs a scheduled job. 'refunded' is also not
# auto-detected (per the approved plan, a refund never demotes a paid
# invoice's status); whether a fully-refunded invoice should flip to
# 'refunded' is deferred.
#
# ----------------------------------------------------------------
# IDEMPOTENCY LIMITATION
# ----------------------------------------------------------------
# There is no DB-level uniqueness on (visit_id, status) — frontends are
# responsible for checking GET /invoices?visit_id=X before creating a
# new invoice for a visit. Duplicate invoices are technically possible
# if a staff member submits the same visit_id twice. A UNIQUE
# constraint on (visit_id) WHERE status != 'void' could be added in v2
# if this becomes a real operational problem.
#
# Authorization: v1 grants billing access to all hospital members.
# Role-based restrictions are a v2 enhancement (Phase 8/9/10 pattern).
# ================================================================

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import InvoiceStatus, LabOrderStatus, PrescriptionStatus
from app.models.billing import Invoice, InvoiceItem
from app.models.doctor import DoctorProfile
from app.models.lab import LabOrder, LabTest
from app.models.patient import Patient
from app.models.prescription import Drug, Prescription, PrescriptionItem
from app.models.visit import Visit
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceItemUpdate,
    InvoiceUpdate,
)
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0.00")

# Prescriptions billed into an auto-generated invoice: finalized scripts
# only — drafts (not finalized) and cancelled scripts are excluded.
_BILLABLE_PRESCRIPTION_STATUSES = (
    PrescriptionStatus.ISSUED.value,
    PrescriptionStatus.DISPENSED.value,
)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

# 'partial' and 'paid' are documented as valid eventual targets of
# 'unpaid'/'partial' but are PAYMENT-DRIVEN — update_invoice rejects a
# PATCH attempting them before consulting this table.
_INVOICE_TRANSITIONS: dict[str, set[str]] = {
    InvoiceStatus.DRAFT.value: {
        InvoiceStatus.UNPAID.value,
        InvoiceStatus.VOID.value,
    },
    InvoiceStatus.UNPAID.value: {
        InvoiceStatus.PARTIAL.value,
        InvoiceStatus.PAID.value,
        InvoiceStatus.VOID.value,
    },
    InvoiceStatus.PARTIAL.value: {
        InvoiceStatus.PAID.value,
        InvoiceStatus.VOID.value,
    },
    InvoiceStatus.PAID.value: set(),
    InvoiceStatus.VOID.value: set(),
    InvoiceStatus.OVERDUE.value: set(),
    InvoiceStatus.REFUNDED.value: set(),
}

_PAYMENT_DRIVEN_STATUSES = {
    InvoiceStatus.PARTIAL.value,
    InvoiceStatus.PAID.value,
}


# ----------------------------------------------------------------
# MONEY HELPERS
# ----------------------------------------------------------------

def _money(value: Decimal) -> Decimal:
    """Quantize a Decimal to 2 places, ROUND_HALF_UP — the storage form
    for every NUMERIC(10,2) money column."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------
# DERIVED-FIELD ASSEMBLY
# ----------------------------------------------------------------

def _attach_totals(invoice: Invoice) -> Invoice:
    """Attach the derived amount_paid / balance_due fields. The
    invoice's `payments` relationship must already be loaded.

    amount_paid is the NET of all payments (a refund is a negative
    payment, so it reduces amount_paid and raises balance_due)."""
    paid = sum((p.amount for p in invoice.payments), _ZERO)
    invoice.amount_paid = _money(paid)
    invoice.balance_due = _money(invoice.total_amount - paid)
    return invoice


def _sorted_detail(invoice: Invoice) -> Invoice:
    """Sort the nested collections for deterministic output and attach
    the derived totals — the InvoiceDetailResponse shape."""
    invoice.items.sort(key=lambda i: i.created_at)
    invoice.payments.sort(key=lambda p: p.paid_at)
    return _attach_totals(invoice)


def _recompute_invoice_totals(invoice: Invoice) -> None:
    """Recompute subtotal and total_amount from the invoice's currently
    loaded line items. Rejects a discount that exceeds the subtotal."""
    subtotal = _money(sum((it.total_price for it in invoice.items), _ZERO))
    discount = invoice.discount_amount or _ZERO
    tax = invoice.tax_amount or _ZERO
    if discount > subtotal:
        raise BadRequestError(
            f"Discount amount {discount} exceeds the invoice subtotal "
            f"{subtotal}."
        )
    invoice.subtotal = subtotal
    invoice.total_amount = _money(subtotal - discount + tax)


# ----------------------------------------------------------------
# INTERNAL LOADERS
# ----------------------------------------------------------------

async def _load_invoice(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    *,
    with_relations: bool = False,
) -> Invoice:
    """Load a non-deleted invoice within the tenant. Cross-tenant,
    missing, or soft-deleted rows surface as NotFoundError (CLAUDE.md
    §13). with_relations eager-loads items and payments."""
    stmt = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.hospital_id == hospital_id,
        Invoice.deleted_at.is_(None),
    )
    if with_relations:
        stmt = stmt.options(
            selectinload(Invoice.items),
            selectinload(Invoice.payments),
        )
    result = await db.execute(stmt)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice", invoice_id)
    return invoice


async def _detail(
    db: AsyncSession, hospital_id: uuid.UUID, invoice_id: uuid.UUID
) -> Invoice:
    """Load an invoice with items + payments and derived totals — the
    InvoiceDetailResponse shape."""
    invoice = await _load_invoice(db, hospital_id, invoice_id, with_relations=True)
    return _sorted_detail(invoice)


# ----------------------------------------------------------------
# AUTO-AGGREGATION
# ----------------------------------------------------------------

async def _aggregate_visit_lines(
    db: AsyncSession, hospital_id: uuid.UUID, visit: Visit
) -> list[tuple[str, int, Decimal]]:
    """
    Build the invoice line items for a visit: the consultation fee, one
    line per billable prescription item, and one line per non-cancelled
    lab order. Returns (description, quantity, unit_price) tuples.

    A NULL consultation_fee / drug.unit_price / lab_test.price is
    treated as 0; a NULL prescription quantity is treated as 0.
    """
    lines: list[tuple[str, int, Decimal]] = []

    doctor = await db.get(DoctorProfile, visit.doctor_id)
    fee = doctor.consultation_fee if doctor is not None else None
    if fee is not None and fee > _ZERO:
        lines.append(("Consultation fee", 1, _money(fee)))

    rx_result = await db.execute(
        select(PrescriptionItem, Drug)
        .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
        .join(Drug, PrescriptionItem.drug_id == Drug.id)
        .where(
            Prescription.visit_id == visit.id,
            Prescription.hospital_id == hospital_id,
            Prescription.status.in_(_BILLABLE_PRESCRIPTION_STATUSES),
        )
        .order_by(PrescriptionItem.created_at.asc())
    )
    for item, drug in rx_result.all():
        quantity = item.quantity or 0
        unit_price = drug.unit_price if drug.unit_price is not None else _ZERO
        lines.append((f"Medication: {drug.name}", quantity, _money(unit_price)))

    lab_result = await db.execute(
        select(LabOrder, LabTest)
        .join(LabTest, LabOrder.test_id == LabTest.id)
        .where(
            LabOrder.visit_id == visit.id,
            LabOrder.hospital_id == hospital_id,
            LabOrder.status != LabOrderStatus.CANCELLED.value,
        )
        .order_by(LabOrder.created_at.asc())
    )
    for order, test in lab_result.all():
        unit_price = test.price if test.price is not None else _ZERO
        lines.append((f"Lab test: {test.name}", 1, _money(unit_price)))

    return lines


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

async def create_invoice(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    payload: InvoiceCreate,
    *,
    created_by: uuid.UUID,
    created_by_membership_id: uuid.UUID,
) -> Invoice:
    """
    Create an invoice. Two mutually-exclusive modes:

    * Manual — payload.items is non-empty. patient_id is taken from
      visit_id if given, else from payload.patient_id (required).
      visit_id, when supplied, is stored only as a link.
    * Auto-from-visit — payload.items is empty and visit_id is given.
      Line items are aggregated from the visit's consultation fee,
      prescriptions, and lab orders.

    The invoice opens in status 'draft'.
    """
    discount = _money(payload.discount_amount)
    tax = _money(payload.tax_amount)
    manual = bool(payload.items)

    line_specs: list[tuple[str, int, Decimal, Optional[uuid.UUID]]] = []
    visit_id: Optional[uuid.UUID] = None

    if manual:
        if payload.visit_id is not None:
            visit = await _require_visit(db, hospital_id, payload.visit_id)
            patient_id = visit.patient_id
            visit_id = visit.id
        elif payload.patient_id is not None:
            patient_id = await _require_patient(db, hospital_id, payload.patient_id)
        else:
            raise BadRequestError(
                "A manual invoice requires either patient_id or visit_id."
            )
        line_specs = [
            (it.description, it.quantity, _money(it.unit_price), it.service_id)
            for it in payload.items
        ]
    elif payload.visit_id is not None:
        visit = await _require_visit(db, hospital_id, payload.visit_id)
        patient_id = visit.patient_id
        visit_id = visit.id
        line_specs = [
            (desc, qty, price, None)
            for (desc, qty, price) in await _aggregate_visit_lines(
                db, hospital_id, visit
            )
        ]
    else:
        raise BadRequestError(
            "Provide either visit_id (auto-aggregate) or a non-empty "
            "items[] array (manual invoice)."
        )

    invoice = Invoice(
        hospital_id=hospital_id,
        patient_id=patient_id,
        visit_id=visit_id,
        status=InvoiceStatus.DRAFT.value,
        discount_amount=discount,
        tax_amount=tax,
        due_date=payload.due_date,
        created_by=created_by,
        created_by_membership_id=created_by_membership_id,
    )
    for description, quantity, unit_price, service_id in line_specs:
        invoice.items.append(
            InvoiceItem(
                hospital_id=hospital_id,
                service_id=service_id,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                total_price=_money(unit_price * quantity),
            )
        )
    _recompute_invoice_totals(invoice)

    db.add(invoice)
    await db.commit()
    logger.info(
        "Invoice created",
        extra={
            "hospital_id": str(hospital_id),
            "invoice_id": str(invoice.id),
            "mode": "manual" if manual else "auto",
            "item_count": len(line_specs),
        },
    )
    return await _detail(db, hospital_id, invoice.id)


async def _require_visit(
    db: AsyncSession, hospital_id: uuid.UUID, visit_id: uuid.UUID
) -> Visit:
    """Load a non-deleted visit within the tenant, else NotFoundError."""
    result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.hospital_id == hospital_id,
            Visit.deleted_at.is_(None),
        )
    )
    visit = result.scalar_one_or_none()
    if visit is None:
        raise NotFoundError("Visit", visit_id)
    return visit


async def _require_patient(
    db: AsyncSession, hospital_id: uuid.UUID, patient_id: uuid.UUID
) -> uuid.UUID:
    """Verify a non-deleted patient exists within the tenant; return the
    patient id."""
    result = await db.execute(
        select(Patient.id).where(
            Patient.id == patient_id,
            Patient.hospital_id == hospital_id,
            Patient.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Patient", patient_id)
    return patient_id


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_invoice(
    db: AsyncSession, hospital_id: uuid.UUID, invoice_id: uuid.UUID
) -> Invoice:
    """Return one invoice with its items, payments, and derived totals.
    An invoice is returned even if its linked visit was soft-deleted."""
    return await _detail(db, hospital_id, invoice_id)


async def list_invoices(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    patient_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict:
    """
    Paginated invoice list scoped to this hospital, ordered by
    created_at DESC. Invoices whose linked visit has been soft-deleted
    are excluded from the list (they remain retrievable by id).
    """
    from datetime import timedelta

    conditions = [
        Invoice.hospital_id == hospital_id,
        Invoice.deleted_at.is_(None),
        or_(Invoice.visit_id.is_(None), Visit.deleted_at.is_(None)),
    ]
    if patient_id is not None:
        conditions.append(Invoice.patient_id == patient_id)
    if status is not None:
        conditions.append(Invoice.status == status)
    if date_from is not None:
        conditions.append(Invoice.created_at >= date_from)
    if date_to is not None:
        conditions.append(Invoice.created_at < date_to + timedelta(days=1))

    stmt = (
        select(Invoice)
        .outerjoin(Visit, Invoice.visit_id == Visit.id)
        .where(*conditions)
        .options(selectinload(Invoice.payments))
        .order_by(Invoice.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    for invoice in items:
        _attach_totals(invoice)
    return make_paged_response(items=items, total=total, page=page, size=size)


async def list_outstanding(
    db: AsyncSession, hospital_id: uuid.UUID
) -> list[Invoice]:
    """
    Invoices with a positive balance_due — money still owed. Covers
    'unpaid' and 'partial' invoices, plus any 'paid' invoice whose
    balance went positive after a refund. 'draft' and 'void' invoices
    are excluded. balance_due is derived, so the filter is applied in
    Python after loading payments.
    """
    result = await db.execute(
        select(Invoice)
        .where(
            Invoice.hospital_id == hospital_id,
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(
                (
                    InvoiceStatus.UNPAID.value,
                    InvoiceStatus.PARTIAL.value,
                    InvoiceStatus.PAID.value,
                )
            ),
        )
        .options(selectinload(Invoice.payments))
        .order_by(Invoice.created_at.desc())
    )
    outstanding: list[Invoice] = []
    for invoice in result.scalars().all():
        _attach_totals(invoice)
        if invoice.balance_due > _ZERO:
            outstanding.append(invoice)
    return outstanding


# ----------------------------------------------------------------
# UPDATE — state machine + draft-only financial edits
# ----------------------------------------------------------------

async def update_invoice(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    *,
    updated_by: uuid.UUID,
    updated_by_membership_id: uuid.UUID,
) -> Invoice:
    """
    Partial update of an invoice. status moves along the invoice state
    machine; 'partial' / 'paid' are payment-driven and rejected here.
    discount_amount / tax_amount / due_date may only be changed while
    the invoice is still 'draft' (after that the line items are locked).
    """
    invoice = await _load_invoice(db, hospital_id, invoice_id, with_relations=True)

    data = payload.model_dump(exclude_unset=True)
    new_status: Optional[InvoiceStatus] = data.pop("status", None)

    financial = {
        k: v
        for k, v in data.items()
        if k in ("discount_amount", "tax_amount", "due_date")
    }
    if financial and invoice.status != InvoiceStatus.DRAFT.value:
        raise BadRequestError(
            "discount_amount, tax_amount, and due_date can only be "
            f"changed while the invoice is in 'draft' (current status: "
            f"'{invoice.status}')."
        )

    money_changed = False
    if "discount_amount" in financial:
        invoice.discount_amount = _money(financial["discount_amount"])
        money_changed = True
    if "tax_amount" in financial:
        invoice.tax_amount = _money(financial["tax_amount"])
        money_changed = True
    if "due_date" in financial:
        invoice.due_date = financial["due_date"]
    if money_changed:
        _recompute_invoice_totals(invoice)

    if new_status is not None and new_status.value != invoice.status:
        target = new_status.value
        if target in _PAYMENT_DRIVEN_STATUSES:
            raise BadRequestError(
                f"Invoice status '{target}' is set automatically when "
                f"payments are recorded; it cannot be set via PATCH."
            )
        allowed = _INVOICE_TRANSITIONS.get(invoice.status, set())
        if target not in allowed:
            logger.warning(
                "Rejected invoice status transition",
                extra={
                    "hospital_id": str(hospital_id),
                    "invoice_id": str(invoice_id),
                },
            )
            raise BadRequestError(
                f"Cannot change invoice status from '{invoice.status}' "
                f"to '{target}'."
            )
        invoice.status = target

    invoice.updated_by = updated_by
    invoice.updated_by_membership_id = updated_by_membership_id

    await db.commit()
    logger.info(
        "Invoice updated",
        extra={
            "hospital_id": str(hospital_id),
            "invoice_id": str(invoice_id),
            "status": invoice.status,
        },
    )
    return await _detail(db, hospital_id, invoice_id)


async def delete_invoice(
    db: AsyncSession, hospital_id: uuid.UUID, invoice_id: uuid.UUID
) -> None:
    """
    Soft-delete an invoice — permitted only while it is still 'draft'.
    A finalized invoice must instead be voided via a status change so
    its billing record is preserved.
    """
    invoice = await _load_invoice(db, hospital_id, invoice_id)
    if invoice.status != InvoiceStatus.DRAFT.value:
        raise BadRequestError(
            f"Only a 'draft' invoice can be deleted (current status: "
            f"'{invoice.status}'). Void it via a status change instead."
        )
    invoice.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "Invoice deleted",
        extra={"hospital_id": str(hospital_id), "invoice_id": str(invoice_id)},
    )


# ----------------------------------------------------------------
# INVOICE ITEMS — sub-resource, draft only
# ----------------------------------------------------------------

def _require_draft_for_items(invoice: Invoice) -> None:
    """Line items may only be changed while the invoice is 'draft'."""
    if invoice.status != InvoiceStatus.DRAFT.value:
        raise BadRequestError(
            f"Invoice line items can only be changed while the invoice "
            f"is in 'draft' (current status: '{invoice.status}')."
        )


async def add_invoice_item(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: InvoiceItemCreate,
    *,
    updated_by: uuid.UUID,
    updated_by_membership_id: uuid.UUID,
) -> Invoice:
    """Append a line item to a draft invoice and recompute its totals."""
    invoice = await _load_invoice(db, hospital_id, invoice_id, with_relations=True)
    _require_draft_for_items(invoice)

    unit_price = _money(payload.unit_price)
    invoice.items.append(
        InvoiceItem(
            hospital_id=hospital_id,
            service_id=payload.service_id,
            description=payload.description,
            quantity=payload.quantity,
            unit_price=unit_price,
            total_price=_money(unit_price * payload.quantity),
        )
    )
    _recompute_invoice_totals(invoice)
    invoice.updated_by = updated_by
    invoice.updated_by_membership_id = updated_by_membership_id

    await db.commit()
    logger.info(
        "Invoice item added",
        extra={"hospital_id": str(hospital_id), "invoice_id": str(invoice_id)},
    )
    return await _detail(db, hospital_id, invoice_id)


async def update_invoice_item(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: InvoiceItemUpdate,
    *,
    updated_by: uuid.UUID,
    updated_by_membership_id: uuid.UUID,
) -> Invoice:
    """Update a draft invoice's line item and recompute its totals."""
    invoice = await _load_invoice(db, hospital_id, invoice_id, with_relations=True)
    _require_draft_for_items(invoice)

    item = next((i for i in invoice.items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Invoice item", item_id)

    data = payload.model_dump(exclude_unset=True)
    if "description" in data:
        item.description = data["description"]
    if "quantity" in data:
        item.quantity = data["quantity"]
    if "unit_price" in data:
        item.unit_price = _money(data["unit_price"])
    if "service_id" in data:
        item.service_id = data["service_id"]
    item.total_price = _money(item.unit_price * item.quantity)

    _recompute_invoice_totals(invoice)
    invoice.updated_by = updated_by
    invoice.updated_by_membership_id = updated_by_membership_id

    await db.commit()
    logger.info(
        "Invoice item updated",
        extra={
            "hospital_id": str(hospital_id),
            "invoice_id": str(invoice_id),
            "invoice_item_id": str(item_id),
        },
    )
    return await _detail(db, hospital_id, invoice_id)


async def delete_invoice_item(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    updated_by: uuid.UUID,
    updated_by_membership_id: uuid.UUID,
) -> None:
    """Remove a line item from a draft invoice and recompute its totals."""
    invoice = await _load_invoice(db, hospital_id, invoice_id, with_relations=True)
    _require_draft_for_items(invoice)

    item = next((i for i in invoice.items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Invoice item", item_id)

    invoice.items.remove(item)
    await db.delete(item)
    _recompute_invoice_totals(invoice)
    invoice.updated_by = updated_by
    invoice.updated_by_membership_id = updated_by_membership_id

    await db.commit()
    logger.info(
        "Invoice item deleted",
        extra={
            "hospital_id": str(hospital_id),
            "invoice_id": str(invoice_id),
            "invoice_item_id": str(item_id),
        },
    )

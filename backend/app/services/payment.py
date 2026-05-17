# ================================================================
# NexusCare — app/services/payment.py
# Payment recording and the revenue report. Payments are APPEND-ONLY:
# there is no update or delete. A refund is a new payment row with a
# NEGATIVE amount (the payments table has no CHECK on amount).
#
# NexusCare never processes money — it only RECORDS that a payment
# happened at the billing counter. There is no gateway integration.
#
# ----------------------------------------------------------------
# CONCURRENCY (approved v1 simplification)
# ----------------------------------------------------------------
# record_payment loads the invoice + its payments, validates, inserts
# the payment, updates the invoice status, and commits in one
# transaction. Two simultaneous payments could in principle both pass
# the overpay check before either commits. The window is tiny and the
# worst case is a stale 'partial' status that self-corrects on the next
# read — no money is lost. Hardening (an advisory lock keyed on
# invoice_id, like services/dispense.py) is deferred to v2.
#
# All queries are hospital-scoped (CLAUDE.md §13).
# ================================================================

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import InvoiceStatus
from app.models.billing import Invoice, Payment
from app.schemas.audit import RequestMetadata
from app.schemas.invoice import PaymentCreate
from app.services import audit as audit_service
from app.utils.exceptions import BadRequestError, NotFoundError

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0.00")

# Invoice statuses against which a payment (or refund) may be recorded.
# 'draft' is not finalized; 'void' is terminal.
_PAYABLE_STATUSES = {
    InvoiceStatus.UNPAID.value,
    InvoiceStatus.PARTIAL.value,
    InvoiceStatus.PAID.value,
}


def _money(value: Decimal) -> Decimal:
    """Quantize a Decimal to 2 places, ROUND_HALF_UP."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


async def _load_invoice(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    *,
    with_payments: bool = False,
) -> Invoice:
    """Load a non-deleted invoice within the tenant, else NotFoundError
    (CLAUDE.md §13)."""
    stmt = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.hospital_id == hospital_id,
        Invoice.deleted_at.is_(None),
    )
    if with_payments:
        stmt = stmt.options(selectinload(Invoice.payments))
    result = await db.execute(stmt)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice", invoice_id)
    return invoice


# ----------------------------------------------------------------
# RECORD A PAYMENT
# ----------------------------------------------------------------

async def record_payment(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: PaymentCreate,
    *,
    recorded_by: uuid.UUID,
    recorded_by_membership_id: uuid.UUID,
    request_meta: Optional[RequestMetadata] = None,
) -> Payment:
    """
    Record a payment against an invoice. A positive amount is a
    payment; a negative amount is a refund.

    The invoice must be finalized ('unpaid', 'partial', or 'paid'). A
    payment may not overpay the invoice; a refund may not exceed the
    amount already paid. On a positive payment the invoice status is
    advanced to 'partial' or 'paid'.
    """
    invoice = await _load_invoice(db, hospital_id, invoice_id, with_payments=True)

    amount = _money(payload.amount)
    if amount == _ZERO:
        raise BadRequestError("Payment amount cannot be zero.")

    if invoice.status not in _PAYABLE_STATUSES:
        raise BadRequestError(
            f"Cannot record a payment against an invoice with status "
            f"'{invoice.status}'. The invoice must be finalized "
            f"('unpaid', 'partial', or 'paid')."
        )

    current_paid = _money(sum((p.amount for p in invoice.payments), _ZERO))
    new_paid = current_paid + amount

    if amount > _ZERO and new_paid > invoice.total_amount:
        raise BadRequestError(
            f"Payment of {amount} would overpay the invoice. The "
            f"outstanding balance is {invoice.total_amount - current_paid}."
        )
    if amount < _ZERO and new_paid < _ZERO:
        raise BadRequestError(
            f"Refund of {-amount} exceeds the amount paid so far "
            f"({current_paid})."
        )

    payment = Payment(
        hospital_id=hospital_id,
        invoice_id=invoice_id,
        amount=amount,
        method=payload.method.value,
        reference=payload.reference,
        recorded_by=recorded_by,
        recorded_by_membership_id=recorded_by_membership_id,
    )
    db.add(payment)
    # Flush so payment.id is populated for the audit row below.
    await db.flush()

    # Status update is driven by POSITIVE payments only.
    # Refunds reduce amount_paid but do not demote status. A 'paid'
    # invoice with a refund stays 'paid' — this preserves the
    # accounting record of when full payment was originally achieved.
    if amount > _ZERO:
        if new_paid >= invoice.total_amount:
            invoice.status = InvoiceStatus.PAID.value
            if invoice.paid_at is None:
                invoice.paid_at = datetime.now(timezone.utc)
        else:
            invoice.status = InvoiceStatus.PARTIAL.value

    invoice.updated_by = recorded_by
    invoice.updated_by_membership_id = recorded_by_membership_id

    # Audit row rides on the same commit as the payment insert and the
    # invoice status change. amount is a Decimal — log_audit stringifies it.
    await audit_service.log_audit(
        db,
        action="record_payment",
        resource_type="invoice",
        resource_id=invoice_id,
        user_id=recorded_by,
        hospital_id=hospital_id,
        membership_id=recorded_by_membership_id,
        new_value={
            "amount": amount,
            "method": payload.method.value,
            "is_refund": amount < _ZERO,
            "payment_id": payment.id,
        },
        request_meta=request_meta,
    )

    await db.commit()
    await db.refresh(payment)
    logger.info(
        "Payment recorded",
        extra={
            "hospital_id": str(hospital_id),
            "invoice_id": str(invoice_id),
            "payment_id": str(payment.id),
            "is_refund": amount < _ZERO,
            "invoice_status": invoice.status,
        },
    )
    return payment


# ----------------------------------------------------------------
# LIST PAYMENTS
# ----------------------------------------------------------------

async def list_payments(
    db: AsyncSession, hospital_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[Payment]:
    """List every payment recorded against an invoice, oldest first."""
    await _load_invoice(db, hospital_id, invoice_id)
    result = await db.execute(
        select(Payment)
        .where(
            Payment.invoice_id == invoice_id,
            Payment.hospital_id == hospital_id,
        )
        .order_by(Payment.paid_at.asc())
    )
    return list(result.scalars().all())


# ----------------------------------------------------------------
# REVENUE REPORT
# ----------------------------------------------------------------

async def revenue_report(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    from_date: date,
    to_date: date,
) -> dict:
    """
    Summarise payments whose paid_at falls within [from_date, to_date]
    (to_date inclusive of the whole day).

    gross   — sum of positive payments
    refunds — sum of refunds (negative payments), reported as positive
    net     — gross - refunds (the true cash position)
    """
    if from_date > to_date:
        raise BadRequestError("from_date must not be after to_date.")

    result = await db.execute(
        select(Payment.amount).where(
            Payment.hospital_id == hospital_id,
            Payment.paid_at >= from_date,
            Payment.paid_at < to_date + timedelta(days=1),
        )
    )
    amounts = [row[0] for row in result.all()]
    gross = sum((a for a in amounts if a > _ZERO), _ZERO)
    refunds = sum((-a for a in amounts if a < _ZERO), _ZERO)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "gross": _money(gross),
        "refunds": _money(refunds),
        "net": _money(gross - refunds),
        "payment_count": len(amounts),
    }

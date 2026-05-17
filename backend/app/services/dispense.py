# ================================================================
# NexusCare — app/services/dispense.py
# The atomic drug-dispensing core. One public function — dispense_item
# — records a single dispense event: it deducts physical stock from a
# drug batch, writes an immutable DispenseLog, and auto-completes the
# prescription once every item is fully dispensed.
#
# ----------------------------------------------------------------
# ATOMICITY CONTRACT (approved Phase 9 refinement #3)
# ----------------------------------------------------------------
# A dispense crosses three tables in one breath (drug_batches,
# dispense_logs, prescriptions). Correctness rests on four guarantees:
#
#   1. SERIALIZATION. Concurrent dispenses of the SAME drug are
#      serialized by a transaction-scoped Postgres advisory lock:
#          pg_advisory_xact_lock(hashtext('dispense:' || drug_id))
#      The lock is acquired AFTER the prescription/item are loaded but
#      BEFORE any stock is read. It releases automatically on commit or
#      rollback. Two callers racing for the last unit of a drug can
#      therefore never both succeed — the second one, once it acquires
#      the lock, reads the stock the first one already wrote.
#
#   2. READ-BEFORE-WRITE. Every read and every validation happens
#      before the first mutation. Stock is read under the lock, so the
#      value validated is the value mutated — no time-of-check /
#      time-of-use gap. Nothing is added to the session until all
#      checks have passed.
#
#   3. SINGLE COMMIT, NO PARTIAL WRITES. There is exactly one
#      db.commit(), at the very end. No try/except wraps the mutations:
#      any exception propagates untouched, the request ends, get_db
#      closes the session, and the open transaction rolls back. A
#      failed dispense therefore leaves NO dispense_logs row and NO
#      stock change — refinement #5 holds by construction.
#
#   4. SNAPSHOT FRESHNESS. Under READ COMMITTED (Postgres default),
#      the post-lock SELECT on drug_batches takes a fresh snapshot, so
#      it observes dispenses committed by any caller that held the lock
#      before us.
#
# Known accepted race: two dispenses for DIFFERENT drugs of the SAME
# prescription hold different advisory locks and run concurrently. If
# each is the final dispense for its own item, neither transaction sees
# the other's not-yet-committed log, so neither flips the prescription
# to 'dispensed' — it can be left in 'issued' while fully dispensed.
# The window is small and the only consequence is a stale status (not
# stock corruption). Hardening would lock on prescription_id as well.
#
# Batch selection is FIFO and SINGLE-BATCH: the earliest-expiry
# non-expired batch that can fulfil the WHOLE quantity on its own. A
# dispense is never auto-split across batches — if no single batch
# suffices, InsufficientStockError is raised. The caller may instead
# name an explicit batch_id.
#
# Expiry: a batch is expired when expiry_date <= today (UTC date) —
# consistent with services/drug.py. Expired batches are never
# dispensable, by auto-selection or by explicit batch_id.
# ================================================================

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import PrescriptionStatus
from app.models.prescription import (
    DispenseLog,
    Drug,
    DrugBatch,
    Prescription,
    PrescriptionItem,
)
from app.schemas.audit import RequestMetadata
from app.schemas.prescription import DispenseRequest
from app.services import audit as audit_service
from app.utils.exceptions import (
    BadRequestError,
    InsufficientStockError,
    NotFoundError,
)
from app.utils.exceptions import ValidationError as BusinessRuleError

logger = logging.getLogger(__name__)


def _today():
    """Current UTC date — the reference point for expiry comparisons."""
    return datetime.now(timezone.utc).date()


# ----------------------------------------------------------------
# BATCH SELECTION
# ----------------------------------------------------------------

async def _select_batch(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    drug_id: uuid.UUID,
    batch_id: Optional[uuid.UUID],
    quantity: int,
    drug_name: str,
) -> DrugBatch:
    """
    Resolve the batch a dispense draws from. Called only after the
    advisory lock is held, so the stock figures here are authoritative.

    * batch_id given — that batch must belong to the drug + hospital,
      be non-expired, and hold at least `quantity` units.
    * batch_id omitted — FIFO: the earliest-expiry non-expired batch
      able to fulfil the whole quantity from a single batch.

    Raises InsufficientStockError when no eligible batch can cover the
    quantity, NotFoundError for an unknown batch_id, BadRequestError
    for an explicitly named expired batch.
    """
    today = _today()

    if batch_id is not None:
        result = await db.execute(
            select(DrugBatch).where(
                DrugBatch.id == batch_id,
                DrugBatch.drug_id == drug_id,
                DrugBatch.hospital_id == hospital_id,
            )
        )
        batch = result.scalar_one_or_none()
        if batch is None:
            raise NotFoundError("Drug batch", batch_id)
        if batch.expiry_date <= today:
            raise BadRequestError(
                f"Batch '{batch.batch_number}' expired on "
                f"{batch.expiry_date.isoformat()} and cannot be dispensed."
            )
        if batch.stock_quantity < quantity:
            raise InsufficientStockError(drug_name, batch.stock_quantity)
        return batch

    result = await db.execute(
        select(DrugBatch)
        .where(
            DrugBatch.drug_id == drug_id,
            DrugBatch.hospital_id == hospital_id,
            DrugBatch.expiry_date > today,
        )
        .order_by(DrugBatch.expiry_date.asc())
    )
    batches = list(result.scalars().all())
    for batch in batches:
        if batch.stock_quantity >= quantity:
            return batch

    # No single non-expired batch can cover the request. Report the
    # largest single-batch availability — total stock would mislead,
    # since dispensing is never split across batches.
    largest = max((b.stock_quantity for b in batches), default=0)
    raise InsufficientStockError(drug_name, largest)


# ----------------------------------------------------------------
# DISPENSE — the atomic core
# ----------------------------------------------------------------

async def dispense_item(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    prescription_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: DispenseRequest,
    *,
    dispensed_by: uuid.UUID,
    dispensed_by_membership_id: uuid.UUID,
    request_meta: Optional[RequestMetadata] = None,
) -> dict:
    """
    Dispense a quantity of one prescription item against a drug batch.

    The prescription must be in status 'issued'. The quantity may not
    exceed the item's remaining prescribed amount. Stock is drawn from
    a single batch (FIFO auto-selection, or an explicit batch_id).

    See the module docstring for the full atomicity contract. In short:
    all reads/validation happen first, under an advisory lock keyed on
    the drug; mutations follow with a single commit; any exception
    rolls the whole thing back leaving no dispense_logs row.
    """
    # === READ + VALIDATE — no mutation occurs in this block ===

    result = await db.execute(
        select(Prescription)
        .options(selectinload(Prescription.items))
        .where(
            Prescription.id == prescription_id,
            Prescription.hospital_id == hospital_id,
        )
    )
    prescription = result.scalar_one_or_none()
    if prescription is None:
        raise NotFoundError("Prescription", prescription_id)

    if prescription.status != PrescriptionStatus.ISSUED.value:
        logger.warning(
            "Dispense rejected — prescription not issued",
            extra={
                "hospital_id": str(hospital_id),
                "prescription_id": str(prescription_id),
            },
        )
        raise BadRequestError(
            "Only an issued prescription can be dispensed "
            f"(current status: '{prescription.status}')."
        )

    item = next((i for i in prescription.items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Prescription item", item_id)
    if item.quantity is None:
        raise BusinessRuleError(
            "This prescription item has no prescribed quantity and "
            "cannot be dispensed."
        )

    drug = await db.get(Drug, item.drug_id)
    drug_name = drug.name if drug is not None else "drug"

    # Advisory lock — held until this transaction commits or rolls back.
    # Acquired before any stock is read so the read is authoritative.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('dispense:' || :drug_id))"),
        {"drug_id": str(item.drug_id)},
    )

    # Post-lock read: how much of this item has already been dispensed.
    already_result = await db.execute(
        select(func.coalesce(func.sum(DispenseLog.quantity_dispensed), 0)).where(
            DispenseLog.prescription_item_id == item_id
        )
    )
    already = int(already_result.scalar_one())
    remaining = item.quantity - already
    if remaining <= 0:
        raise BusinessRuleError(
            f"This prescription item is already fully dispensed "
            f"({already}/{item.quantity})."
        )
    if payload.quantity > remaining:
        raise BusinessRuleError(
            f"Dispense quantity {payload.quantity} exceeds the remaining "
            f"prescribed amount ({remaining})."
        )

    # Post-lock read: pick the batch to draw from.
    batch = await _select_batch(
        db, hospital_id, item.drug_id, payload.batch_id, payload.quantity, drug_name
    )

    # === MUTATE — single transaction, single commit at the end ===

    batch.stock_quantity -= payload.quantity

    log = DispenseLog(
        hospital_id=hospital_id,
        prescription_item_id=item_id,
        batch_id=batch.id,
        quantity_dispensed=payload.quantity,
        dispensed_by=dispensed_by,
        dispensed_by_membership_id=dispensed_by_membership_id,
        notes=payload.notes,
    )
    db.add(log)
    # Flush so the new log is visible to the totals query below within
    # this same transaction.
    await db.flush()

    # Auto-complete: flip the prescription to 'dispensed' once every
    # item has been dispensed in full.
    totals_result = await db.execute(
        select(
            DispenseLog.prescription_item_id,
            func.sum(DispenseLog.quantity_dispensed),
        )
        .where(
            DispenseLog.prescription_item_id.in_(
                [i.id for i in prescription.items]
            )
        )
        .group_by(DispenseLog.prescription_item_id)
    )
    totals = {row[0]: int(row[1]) for row in totals_result.all()}
    all_fully_dispensed = all(
        i.quantity is not None and totals.get(i.id, 0) >= i.quantity
        for i in prescription.items
    )
    if all_fully_dispensed:
        prescription.status = PrescriptionStatus.DISPENSED.value

    # Audit row rides on the same single commit as the stock deduction
    # and the dispense log — a rolled-back dispense leaves no audit row.
    await audit_service.log_audit(
        db,
        action="dispense",
        resource_type="prescription_item",
        resource_id=item_id,
        user_id=dispensed_by,
        hospital_id=hospital_id,
        membership_id=dispensed_by_membership_id,
        new_value={
            "batch_id": batch.id,
            "quantity": payload.quantity,
            "dispense_log_id": log.id,
        },
        request_meta=request_meta,
    )

    await db.commit()
    await db.refresh(log)
    await db.refresh(batch)

    item_dispensed = already + payload.quantity
    logger.info(
        "Drug dispensed",
        extra={
            "hospital_id": str(hospital_id),
            "prescription_id": str(prescription_id),
            "prescription_item_id": str(item_id),
            "batch_id": str(batch.id),
            "dispense_log_id": str(log.id),
        },
    )
    return {
        "dispense_log_id": log.id,
        "dispense_log": log,
        "batch_remaining_stock": batch.stock_quantity,
        "item_dispensed_quantity": item_dispensed,
        "item_remaining_quantity": item.quantity - item_dispensed,
        "item_fully_dispensed": item_dispensed >= item.quantity,
        "prescription_status": prescription.status,
    }

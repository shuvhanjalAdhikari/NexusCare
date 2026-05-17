# ================================================================
# NexusCare — app/services/prescription.py
# Prescription business logic: nested create (with items), read,
# listing, and the prescription state machine. All queries are
# hospital-scoped (CLAUDE.md §13).
#
# Dispensing logic does NOT live here — it lives in services/dispense.py
# (the atomic stock-deduction core). This module only owns the
# draft → issued → dispensed | cancelled lifecycle.
#
# Prescription state machine (PATCH /prescriptions transitions only):
#   draft   → issued | cancelled
#   issued  → dispensed | cancelled
#   dispensed / cancelled → terminal
# 'dispensed' is NEVER set via PATCH — services/dispense.py sets it
# automatically once every item is fully dispensed. A PATCH attempting
# status='dispensed' is rejected with BadRequestError.
# issued_at is stamped the first time a prescription enters 'issued'.
#
# Authorization: v1 grants prescription access to all hospital members.
# Role-based restrictions (e.g. doctor-only issue, pharmacist-only
# dispense) are a v2 enhancement.
#
# Derived fields: prescription_items has no stored dispense counter.
# dispensed_quantity / remaining_quantity / is_fully_dispensed are
# computed from the item's dispense_logs and attached to the ORM
# instance before it is serialized (see _attach_progress).
#
# Orphan rule: a prescription whose parent visit is later soft-deleted
# is left reachable via /api/v1/prescriptions — unlike referrals,
# prescriptions are not joined back to the visit. The visit is verified
# non-deleted only at create time. Orphan exclusion is a v2 decision.
# ================================================================

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import PrescriptionStatus, VisitStatus
from app.models.prescription import Drug, Prescription, PrescriptionItem
from app.models.visit import Visit
from app.schemas.audit import RequestMetadata
from app.schemas.prescription import PrescriptionCreate, PrescriptionUpdate
from app.services import audit as audit_service
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

# 'dispensed' appears as a valid target of 'issued' to document the
# real lifecycle, but PATCH callers can never reach it — the explicit
# guard in update_prescription rejects status='dispensed' first.
_PRESCRIPTION_TRANSITIONS: dict[str, set[str]] = {
    PrescriptionStatus.DRAFT.value: {
        PrescriptionStatus.ISSUED.value,
        PrescriptionStatus.CANCELLED.value,
    },
    PrescriptionStatus.ISSUED.value: {
        PrescriptionStatus.DISPENSED.value,
        PrescriptionStatus.CANCELLED.value,
    },
    PrescriptionStatus.DISPENSED.value: set(),
    PrescriptionStatus.CANCELLED.value: set(),
}


# Visit statuses against which a new prescription may be created. A
# 'waiting' visit has no consultation under way; a 'closed' visit is a
# finalized record; a 'cancelled' visit never happened. Mirrors
# services/lab.py::create_lab_order (Phase 14 — closes the Phase 9 gap).
_PRESCRIBABLE_VISIT_STATUSES = {
    VisitStatus.ACTIVE.value,
    VisitStatus.COMPLETED.value,
}


# ----------------------------------------------------------------
# DERIVED-FIELD ASSEMBLY
# ----------------------------------------------------------------

def _attach_progress(prescription: Prescription) -> Prescription:
    """
    Attach the derived dispensing-progress fields to every item of an
    eagerly-loaded prescription. Each item must have its dispense_logs
    relationship already populated.

    Items are sorted by created_at and each item's dispense_logs by
    dispensed_at so the serialized output is deterministic.
    """
    prescription.items.sort(key=lambda i: i.created_at)
    for item in prescription.items:
        item.dispense_logs.sort(key=lambda log: log.dispensed_at)
        dispensed = sum(log.quantity_dispensed for log in item.dispense_logs)
        prescribed = item.quantity or 0
        item.dispensed_quantity = dispensed
        item.remaining_quantity = max(prescribed - dispensed, 0)
        item.is_fully_dispensed = (
            item.quantity is not None and dispensed >= item.quantity
        )
    return prescription


# ----------------------------------------------------------------
# INTERNAL LOADERS
# ----------------------------------------------------------------

async def _load_prescription(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    prescription_id: uuid.UUID,
    *,
    with_items: bool = False,
) -> Prescription:
    """Load a prescription within the tenant. Cross-tenant or missing
    rows surface as NotFoundError (CLAUDE.md §13).

    with_items eager-loads items and each item's dispense_logs."""
    stmt = select(Prescription).where(
        Prescription.id == prescription_id,
        Prescription.hospital_id == hospital_id,
    )
    if with_items:
        stmt = stmt.options(
            selectinload(Prescription.items).selectinload(
                PrescriptionItem.dispense_logs
            )
        )
    result = await db.execute(stmt)
    prescription = result.scalar_one_or_none()
    if prescription is None:
        raise NotFoundError("Prescription", prescription_id)
    return prescription


async def _detail(
    db: AsyncSession, hospital_id: uuid.UUID, prescription_id: uuid.UUID
) -> Prescription:
    """Load a prescription with items + dispense history and the derived
    progress fields attached — the PrescriptionDetailResponse shape."""
    prescription = await _load_prescription(
        db, hospital_id, prescription_id, with_items=True
    )
    return _attach_progress(prescription)


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_prescription(
    db: AsyncSession, hospital_id: uuid.UUID, prescription_id: uuid.UUID
) -> Prescription:
    """Return one prescription with its items, each carrying derived
    dispensing progress and full dispense history."""
    return await _detail(db, hospital_id, prescription_id)


async def list_prescriptions(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    visit_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> dict:
    """
    Paginated prescription list scoped to this hospital, ordered by
    created_at DESC. The flat PrescriptionResponse shape — items are
    not included in the list view.
    """
    conditions = [Prescription.hospital_id == hospital_id]
    if visit_id is not None:
        conditions.append(Prescription.visit_id == visit_id)
    if patient_id is not None:
        conditions.append(Prescription.patient_id == patient_id)
    if doctor_id is not None:
        conditions.append(Prescription.doctor_id == doctor_id)
    if status is not None:
        conditions.append(Prescription.status == status)

    stmt = (
        select(Prescription)
        .where(*conditions)
        .order_by(Prescription.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# CREATE — nested under a visit
# ----------------------------------------------------------------

async def create_prescription(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: PrescriptionCreate,
    *,
    created_by: uuid.UUID,
    created_by_membership_id: uuid.UUID,
) -> Prescription:
    """
    Create a prescription with its items during a visit. The
    prescription opens in status 'draft'. patient_id / doctor_id are
    taken from the visit — never from the request body.

    Every referenced drug is verified to belong to this hospital; an
    inactive drug cannot be referenced by a new prescription item.
    """
    # The visit must exist within the tenant, not be soft-deleted, and
    # be in a status that admits new clinical orders. This check runs
    # before any drug validation — same rule as create_lab_order.
    visit_result = await db.execute(
        select(Visit).where(
            Visit.id == visit_id,
            Visit.hospital_id == hospital_id,
            Visit.deleted_at.is_(None),
        )
    )
    visit = visit_result.scalar_one_or_none()
    if visit is None:
        raise NotFoundError("Visit", visit_id)
    if visit.status not in _PRESCRIBABLE_VISIT_STATUSES:
        raise BadRequestError(
            f"Cannot create a prescription on a visit with status "
            f"'{visit.status}'. The visit must be active or completed."
        )

    drug_ids = {item.drug_id for item in payload.items}
    drug_result = await db.execute(
        select(Drug).where(
            Drug.id.in_(drug_ids),
            Drug.hospital_id == hospital_id,
        )
    )
    drugs = {drug.id: drug for drug in drug_result.scalars().all()}
    for drug_id in drug_ids:
        drug = drugs.get(drug_id)
        if drug is None:
            raise NotFoundError("Drug", drug_id)
        if not drug.is_active:
            raise BadRequestError(
                f"Drug '{drug_id}' is inactive and cannot be prescribed."
            )

    prescription = Prescription(
        hospital_id=hospital_id,
        visit_id=visit_id,
        patient_id=visit.patient_id,
        doctor_id=visit.doctor_id,
        status=PrescriptionStatus.DRAFT.value,
        notes=payload.notes,
        created_by=created_by,
        created_by_membership_id=created_by_membership_id,
    )
    for item_payload in payload.items:
        prescription.items.append(
            PrescriptionItem(
                hospital_id=hospital_id,
                **item_payload.model_dump(),
            )
        )
    db.add(prescription)
    await db.commit()
    logger.info(
        "Prescription created",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "prescription_id": str(prescription.id),
            "item_count": len(payload.items),
        },
    )
    return await _detail(db, hospital_id, prescription.id)


# ----------------------------------------------------------------
# UPDATE — notes + status state machine
# ----------------------------------------------------------------

async def update_prescription(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    prescription_id: uuid.UUID,
    payload: PrescriptionUpdate,
    *,
    updated_by: uuid.UUID,
    updated_by_membership_id: uuid.UUID,
    request_meta: Optional[RequestMetadata] = None,
) -> Prescription:
    """
    Partial update of a prescription's notes and/or status. A status
    change is validated against the prescription state machine;
    entering 'issued' stamps issued_at the first time.

    status='dispensed' is rejected — it is set automatically by the
    dispensing flow once every item is fully dispensed.

    Audit: a transition to 'cancelled' writes a 'cancel_prescription'
    audit row in the same transaction. Other transitions are not
    audited in v1 (see services/audit.py deferred-TODO list).
    """
    prescription = await _load_prescription(db, hospital_id, prescription_id)

    data = payload.model_dump(exclude_unset=True)
    new_status: Optional[PrescriptionStatus] = data.pop("status", None)

    if new_status is not None and new_status.value != prescription.status:
        target = new_status.value
        previous_status = prescription.status
        if target == PrescriptionStatus.DISPENSED.value:
            raise BadRequestError(
                "Prescription status 'dispensed' is set automatically once "
                "every item is fully dispensed; it cannot be set manually."
            )
        allowed = _PRESCRIPTION_TRANSITIONS.get(prescription.status, set())
        if target not in allowed:
            logger.warning(
                "Rejected prescription status transition",
                extra={
                    "hospital_id": str(hospital_id),
                    "prescription_id": str(prescription_id),
                },
            )
            raise BadRequestError(
                f"Cannot change prescription status from "
                f"'{prescription.status}' to '{target}'."
            )
        prescription.status = target
        if (
            target == PrescriptionStatus.ISSUED.value
            and prescription.issued_at is None
        ):
            prescription.issued_at = datetime.now(timezone.utc)

        if target == PrescriptionStatus.CANCELLED.value:
            await audit_service.log_audit(
                db,
                action="cancel_prescription",
                resource_type="prescription",
                resource_id=prescription.id,
                user_id=updated_by,
                hospital_id=hospital_id,
                membership_id=updated_by_membership_id,
                old_value={"status": previous_status},
                new_value={"status": target},
                request_meta=request_meta,
            )

    for field, value in data.items():
        setattr(prescription, field, value)

    prescription.updated_by = updated_by
    prescription.updated_by_membership_id = updated_by_membership_id

    await db.commit()
    await db.refresh(prescription)
    logger.info(
        "Prescription updated",
        extra={
            "hospital_id": str(hospital_id),
            "prescription_id": str(prescription_id),
            "status": prescription.status,
        },
    )
    return prescription

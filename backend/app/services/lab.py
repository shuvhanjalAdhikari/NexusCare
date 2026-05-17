# ================================================================
# NexusCare — app/services/lab.py
# Diagnostic lab business logic: the per-hospital lab-test catalogue,
# lab orders raised during a visit, and the one-to-one lab result.
# All queries are hospital-scoped (CLAUDE.md §13).
#
# ----------------------------------------------------------------
# LAB-TEST CATALOGUE
# ----------------------------------------------------------------
# lab_tests is per-hospital reference data. Entries are NEVER deleted:
# a lab_order references its test by FK, so removing a test would
# orphan historical orders. Deactivation is via PATCH is_active=false;
# an inactive test can no longer be ordered but stays referenceable.
#
# ----------------------------------------------------------------
# LAB-ORDER STATE MACHINE (PATCH /lab-orders transitions only)
# ----------------------------------------------------------------
#   ordered      → collected | cancelled
#   collected    → in_progress | cancelled
#   in_progress  → result_ready
#   result_ready → reviewed
#   reviewed / cancelled → terminal
#
# Cancellation is allowed ONLY from 'ordered' or 'collected' — before
# the lab actually starts work. Once an order is 'in_progress' it can
# no longer be cancelled: the lab is mid-analysis.
#
#   * entering 'collected'  stamps sample_collected_at (once)
#   * entering 'result_ready' stamps result_ready_at (once) and
#     REQUIRES a lab result row to already exist — there is nothing to
#     mark "ready" otherwise.
#   * entering 'reviewed' requires the order be 'result_ready' and
#     stamps reviewed_by / reviewed_by_membership_id / reviewed_at on
#     the RESULT row (lab_orders carries no review audit columns).
#
# ----------------------------------------------------------------
# LAB RESULT — one-to-one with the order
# ----------------------------------------------------------------
# lab_results.lab_order_id is UNIQUE: an order has at most one result.
# A result may be entered only while the order is 'in_progress'; a
# second POST surfaces as ConflictError. Corrections (PATCH/DELETE) are
# allowed while 'in_progress' or 'result_ready', never once 'reviewed'
# — the doctor has already signed off. A correction never changes
# uploaded_by; the original lab technician stays on record.
#
# Authorization: v1 grants lab access to all hospital members. The
# audit columns record who actually performed each action; role-based
# restrictions are a v2 enhancement (Phase 8/9 pattern).
# ================================================================

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import LabOrderStatus, VisitStatus
from app.models.lab import LabOrder, LabResult, LabTest
from app.models.visit import Visit
from app.schemas.lab import (
    LabOrderCreate,
    LabOrderUpdate,
    LabResultCreate,
    LabResultUpdate,
    LabTestCreate,
    LabTestUpdate,
)
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

_LAB_ORDER_TRANSITIONS: dict[str, set[str]] = {
    LabOrderStatus.ORDERED.value: {
        LabOrderStatus.COLLECTED.value,
        LabOrderStatus.CANCELLED.value,
    },
    LabOrderStatus.COLLECTED.value: {
        LabOrderStatus.IN_PROGRESS.value,
        LabOrderStatus.CANCELLED.value,
    },
    LabOrderStatus.IN_PROGRESS.value: {
        LabOrderStatus.RESULT_READY.value,
    },
    LabOrderStatus.RESULT_READY.value: {
        LabOrderStatus.REVIEWED.value,
    },
    LabOrderStatus.REVIEWED.value: set(),
    LabOrderStatus.CANCELLED.value: set(),
}

# Visit statuses against which a new lab order may be raised. A closed
# visit is a finalized record; a cancelled / waiting visit has no
# active consultation to attach an order to.
_ORDERABLE_VISIT_STATUSES = {
    VisitStatus.ACTIVE.value,
    VisitStatus.COMPLETED.value,
}

# Order statuses during which a result may be created / corrected.
_RESULT_EDITABLE_STATUSES = {
    LabOrderStatus.IN_PROGRESS.value,
    LabOrderStatus.RESULT_READY.value,
}


def _now() -> datetime:
    """Current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------
# DERIVED-FIELD ASSEMBLY
# ----------------------------------------------------------------

def _attach_order_fields(order: LabOrder) -> LabOrder:
    """Attach the derived fields (test_name, has_result) the response
    schemas expect. The order's `test` and `result` relationships must
    already be loaded."""
    order.test_name = order.test.name
    order.has_result = order.result is not None
    return order


# ----------------------------------------------------------------
# INTERNAL LOADERS
# ----------------------------------------------------------------

async def _load_test(
    db: AsyncSession, hospital_id: uuid.UUID, test_id: uuid.UUID
) -> LabTest:
    """Load a lab-test catalogue entry within the tenant. Cross-tenant
    or missing rows surface as NotFoundError (CLAUDE.md §13)."""
    result = await db.execute(
        select(LabTest).where(
            LabTest.id == test_id,
            LabTest.hospital_id == hospital_id,
        )
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise NotFoundError("Lab test", test_id)
    return test


async def _load_order(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    with_relations: bool = False,
) -> LabOrder:
    """Load a lab order within the tenant. Cross-tenant or missing rows
    surface as NotFoundError (CLAUDE.md §13).

    with_relations eager-loads the test catalogue entry and the result."""
    stmt = select(LabOrder).where(
        LabOrder.id == order_id,
        LabOrder.hospital_id == hospital_id,
    )
    if with_relations:
        stmt = stmt.options(
            selectinload(LabOrder.test),
            selectinload(LabOrder.result),
        )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise NotFoundError("Lab order", order_id)
    return order


async def _detail(
    db: AsyncSession, hospital_id: uuid.UUID, order_id: uuid.UUID
) -> LabOrder:
    """Load a lab order with its test + result and the derived fields
    attached — the LabOrderDetailResponse shape."""
    order = await _load_order(db, hospital_id, order_id, with_relations=True)
    return _attach_order_fields(order)


# ================================================================
# LAB-TEST CATALOGUE
# ================================================================

async def create_lab_test(
    db: AsyncSession, hospital_id: uuid.UUID, payload: LabTestCreate
) -> LabTest:
    """Create a lab-test catalogue entry for this hospital."""
    test = LabTest(hospital_id=hospital_id, **payload.model_dump())
    db.add(test)
    await db.commit()
    await db.refresh(test)
    logger.info(
        "Lab test created",
        extra={"hospital_id": str(hospital_id), "lab_test_id": str(test.id)},
    )
    return test


async def list_lab_tests(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    *,
    q: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> list[LabTest]:
    """List this hospital's lab-test catalogue, ordered by name. Optional
    case-insensitive name substring filter and is_active filter."""
    conditions = [LabTest.hospital_id == hospital_id]
    if q:
        conditions.append(LabTest.name.ilike(f"%{q}%"))
    if is_active is not None:
        conditions.append(LabTest.is_active.is_(is_active))

    result = await db.execute(
        select(LabTest).where(*conditions).order_by(LabTest.name.asc())
    )
    return list(result.scalars().all())


async def get_lab_test(
    db: AsyncSession, hospital_id: uuid.UUID, test_id: uuid.UUID
) -> LabTest:
    """Return one lab-test catalogue entry."""
    return await _load_test(db, hospital_id, test_id)


async def update_lab_test(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    test_id: uuid.UUID,
    payload: LabTestUpdate,
) -> LabTest:
    """Partial update of a lab-test catalogue entry. Setting
    is_active=false deactivates it (lab tests are never hard-deleted)."""
    test = await _load_test(db, hospital_id, test_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(test, field, value)
    await db.commit()
    await db.refresh(test)
    logger.info(
        "Lab test updated",
        extra={"hospital_id": str(hospital_id), "lab_test_id": str(test_id)},
    )
    return test


# ================================================================
# LAB ORDERS
# ================================================================

async def create_lab_order(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: LabOrderCreate,
    *,
    created_by: uuid.UUID,
    created_by_membership_id: uuid.UUID,
) -> LabOrder:
    """
    Order a diagnostic test during a visit. The order opens in status
    'ordered'. patient_id / doctor_id are taken from the visit — never
    from the request body.

    The visit must be 'active' or 'completed' (a closed visit is a
    finalized record). The referenced lab test must belong to this
    hospital and be active.
    """
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
    if visit.status not in _ORDERABLE_VISIT_STATUSES:
        raise BadRequestError(
            f"Cannot order a lab test on a visit with status "
            f"'{visit.status}'. The visit must be active or completed."
        )

    test = await _load_test(db, hospital_id, payload.test_id)
    if not test.is_active:
        raise BadRequestError(
            f"Lab test '{test.name}' is inactive and cannot be ordered."
        )

    order = LabOrder(
        hospital_id=hospital_id,
        visit_id=visit_id,
        patient_id=visit.patient_id,
        doctor_id=visit.doctor_id,
        test_id=payload.test_id,
        priority=payload.priority.value,
        status=LabOrderStatus.ORDERED.value,
        created_by=created_by,
        created_by_membership_id=created_by_membership_id,
    )
    db.add(order)
    await db.commit()
    logger.info(
        "Lab order created",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "lab_order_id": str(order.id),
        },
    )
    return await _detail(db, hospital_id, order.id)


async def list_lab_orders(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    status: Optional[str] = None,
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    visit_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict:
    """
    Paginated lab-order list scoped to this hospital, ordered by
    created_at DESC. date_from / date_to filter on the order's
    created_at (date_to is inclusive of the whole day). The flat
    LabOrderResponse shape — test_name and has_result are attached.
    """
    conditions = [LabOrder.hospital_id == hospital_id]
    if status is not None:
        conditions.append(LabOrder.status == status)
    if doctor_id is not None:
        conditions.append(LabOrder.doctor_id == doctor_id)
    if patient_id is not None:
        conditions.append(LabOrder.patient_id == patient_id)
    if visit_id is not None:
        conditions.append(LabOrder.visit_id == visit_id)
    if date_from is not None:
        conditions.append(LabOrder.created_at >= date_from)
    if date_to is not None:
        conditions.append(LabOrder.created_at < date_to + timedelta(days=1))

    stmt = (
        select(LabOrder)
        .where(*conditions)
        .options(selectinload(LabOrder.test), selectinload(LabOrder.result))
        .order_by(LabOrder.created_at.desc())
    )
    items, total = await paginate(db, stmt, page, size)
    for order in items:
        _attach_order_fields(order)
    return make_paged_response(items=items, total=total, page=page, size=size)


async def get_lab_order(
    db: AsyncSession, hospital_id: uuid.UUID, order_id: uuid.UUID
) -> LabOrder:
    """Return one lab order with its test catalogue entry and result."""
    return await _detail(db, hospital_id, order_id)


async def update_lab_order(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: LabOrderUpdate,
    *,
    reviewed_by: uuid.UUID,
    reviewed_by_membership_id: uuid.UUID,
) -> LabOrder:
    """
    Move a lab order along its state machine. The only mutable field on
    an order is its status.

    * → 'collected'    stamps sample_collected_at.
    * → 'result_ready' stamps result_ready_at and requires a result row
      to already exist.
    * → 'reviewed'     stamps the result's reviewed_by / _membership_id
      / reviewed_at — the doctor's sign-off.

    reviewed_by identifies the caller and is recorded only on the
    'reviewed' transition.
    """
    order = await _load_order(db, hospital_id, order_id, with_relations=True)

    new_status: Optional[LabOrderStatus] = payload.status
    if new_status is None or new_status.value == order.status:
        return _attach_order_fields(order)

    target = new_status.value
    allowed = _LAB_ORDER_TRANSITIONS.get(order.status, set())
    if target not in allowed:
        logger.warning(
            "Rejected lab order status transition",
            extra={
                "hospital_id": str(hospital_id),
                "lab_order_id": str(order_id),
            },
        )
        raise BadRequestError(
            f"Cannot change lab order status from '{order.status}' "
            f"to '{target}'."
        )

    if target == LabOrderStatus.RESULT_READY.value and order.result is None:
        raise BadRequestError(
            "Cannot mark order as result_ready: no result has been "
            "entered yet."
        )

    order.status = target
    if (
        target == LabOrderStatus.COLLECTED.value
        and order.sample_collected_at is None
    ):
        order.sample_collected_at = _now()
    elif (
        target == LabOrderStatus.RESULT_READY.value
        and order.result_ready_at is None
    ):
        order.result_ready_at = _now()
    elif target == LabOrderStatus.REVIEWED.value:
        # The 'result_ready' guard above guarantees a result exists by
        # the time the order can reach 'reviewed'.
        order.result.reviewed_by = reviewed_by
        order.result.reviewed_by_membership_id = reviewed_by_membership_id
        order.result.reviewed_at = _now()

    await db.commit()
    logger.info(
        "Lab order status updated",
        extra={
            "hospital_id": str(hospital_id),
            "lab_order_id": str(order_id),
            "status": target,
        },
    )
    return await _detail(db, hospital_id, order_id)


async def delete_lab_order(
    db: AsyncSession, hospital_id: uuid.UUID, order_id: uuid.UUID
) -> None:
    """
    Hard-delete a lab order. Permitted ONLY while the order is still
    'ordered' — once a sample has been collected the order has lab
    history and must instead be cancelled via a status transition.
    """
    order = await _load_order(db, hospital_id, order_id)
    if order.status != LabOrderStatus.ORDERED.value:
        raise BadRequestError(
            f"A lab order can only be deleted while in status 'ordered' "
            f"(current status: '{order.status}'). Cancel it via a status "
            f"change instead."
        )
    await db.delete(order)
    await db.commit()
    logger.info(
        "Lab order deleted",
        extra={"hospital_id": str(hospital_id), "lab_order_id": str(order_id)},
    )


# ================================================================
# LAB RESULTS — one-to-one sub-resource of a lab order
# ================================================================

async def create_lab_result(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: LabResultCreate,
    *,
    uploaded_by: uuid.UUID,
    uploaded_by_membership_id: uuid.UUID,
) -> LabResult:
    """
    Record the result for a lab order. An order has at most one result
    (lab_order_id is UNIQUE); a second attempt raises ConflictError.

    A result may only be entered while the order is 'in_progress' — the
    sample must have been collected and analysis started.
    """
    order = await _load_order(db, hospital_id, order_id, with_relations=True)

    if order.status != LabOrderStatus.IN_PROGRESS.value:
        raise BadRequestError(
            f"A result can only be entered while the order is "
            f"'in_progress' (current status: '{order.status}')."
        )
    if order.result is not None:
        raise ConflictError(
            "This lab order already has a result. Correct the existing "
            "result instead of adding a new one."
        )

    result = LabResult(
        hospital_id=hospital_id,
        lab_order_id=order_id,
        uploaded_by=uploaded_by,
        uploaded_by_membership_id=uploaded_by_membership_id,
        **payload.model_dump(),
    )
    db.add(result)
    await db.commit()
    await db.refresh(result)
    logger.info(
        "Lab result recorded",
        extra={
            "hospital_id": str(hospital_id),
            "lab_order_id": str(order_id),
            "lab_result_id": str(result.id),
        },
    )
    return result


async def get_lab_result(
    db: AsyncSession, hospital_id: uuid.UUID, order_id: uuid.UUID
) -> LabResult:
    """Return the result for a lab order. NotFoundError if the order has
    no result yet (or the order is cross-tenant / missing)."""
    order = await _load_order(db, hospital_id, order_id, with_relations=True)
    if order.result is None:
        raise NotFoundError("Lab result", order_id)
    return order.result


async def update_lab_result(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: LabResultUpdate,
) -> LabResult:
    """
    Correct a lab result. Permitted while the order is 'in_progress' or
    'result_ready' — never once 'reviewed', as the doctor has already
    signed off. uploaded_by is left untouched so the original lab
    technician stays on record.
    """
    order = await _load_order(db, hospital_id, order_id, with_relations=True)
    if order.result is None:
        raise NotFoundError("Lab result", order_id)
    if order.status not in _RESULT_EDITABLE_STATUSES:
        raise BadRequestError(
            f"A result can only be corrected while the order is "
            f"'in_progress' or 'result_ready' (current status: "
            f"'{order.status}')."
        )

    result = order.result
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(result, field, value)
    await db.commit()
    await db.refresh(result)
    logger.info(
        "Lab result corrected",
        extra={
            "hospital_id": str(hospital_id),
            "lab_order_id": str(order_id),
            "lab_result_id": str(result.id),
        },
    )
    return result


async def delete_lab_result(
    db: AsyncSession, hospital_id: uuid.UUID, order_id: uuid.UUID
) -> None:
    """
    Hard-delete a lab result. Permitted while the order is 'in_progress'
    or 'result_ready' — never once 'reviewed'.
    """
    order = await _load_order(db, hospital_id, order_id, with_relations=True)
    if order.result is None:
        raise NotFoundError("Lab result", order_id)
    if order.status not in _RESULT_EDITABLE_STATUSES:
        raise BadRequestError(
            f"A result can only be deleted while the order is "
            f"'in_progress' or 'result_ready' (current status: "
            f"'{order.status}')."
        )
    await db.delete(order.result)
    await db.commit()
    logger.info(
        "Lab result deleted",
        extra={"hospital_id": str(hospital_id), "lab_order_id": str(order_id)},
    )

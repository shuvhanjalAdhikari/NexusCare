# ================================================================
# NexusCare — app/services/drug.py
# Drug catalogue + batch inventory business logic + stock queries.
# All queries are hospital-scoped (CLAUDE.md §13).
#
# Authorization: v1 grants drug/inventory access to all hospital
# members. Role-based restrictions (e.g. pharmacist-only) are a v2
# enhancement.
#
# Controlled substances: the `drugs` table has NO is_controlled
# column. v1 has no controlled-substance concept — a hospital may tag
# such drugs using the free-text `category` field (e.g.
# category='controlled'), but nothing is enforced. A real is_controlled
# flag plus a dual-signature dispensing workflow is a v2 enhancement
# and would require a schema migration.
#
# Soft delete: `drugs` has no deleted_at column. "Deleting" a drug
# means setting is_active=false — it disappears from the default
# catalogue listing and cannot be referenced by NEW prescription items,
# but existing prescriptions and in-stock batches remain dispensable.
# drug_batches are hard-deleted (a batch received in error is removed).
#
# Expiry: a batch is "expired" when expiry_date <= today (UTC date) —
# conservative, a batch expiring today is treated as expired. Expired
# batches are excluded from all stock totals and from dispensing, but
# are never auto-deleted (audit trail).
# ================================================================

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prescription import Drug, DrugBatch
from app.schemas.drug import (
    BatchCreate,
    BatchUpdate,
    DrugCreate,
    DrugUpdate,
)
from app.utils.exceptions import NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)

# Batches expiring within this many days count as "near expiry".
NEAR_EXPIRY_DAYS = 30


def _today():
    """Current UTC date — the reference point for expiry comparisons."""
    return datetime.now(timezone.utc).date()


# ----------------------------------------------------------------
# INTERNAL LOADERS
# ----------------------------------------------------------------

async def _load_drug(
    db: AsyncSession, hospital_id: uuid.UUID, drug_id: uuid.UUID
) -> Drug:
    """Load a drug within the tenant regardless of is_active. Cross-tenant
    or missing rows surface as NotFoundError (CLAUDE.md §13)."""
    result = await db.execute(
        select(Drug).where(
            Drug.id == drug_id,
            Drug.hospital_id == hospital_id,
        )
    )
    drug = result.scalar_one_or_none()
    if drug is None:
        raise NotFoundError("Drug", drug_id)
    return drug


async def _load_batch(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    drug_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> DrugBatch:
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
    return batch


async def _total_active_stock(
    db: AsyncSession, hospital_id: uuid.UUID, drug_id: uuid.UUID
) -> int:
    """Sum of stock_quantity across this drug's non-expired batches."""
    result = await db.execute(
        select(func.coalesce(func.sum(DrugBatch.stock_quantity), 0)).where(
            DrugBatch.drug_id == drug_id,
            DrugBatch.hospital_id == hospital_id,
            DrugBatch.expiry_date > _today(),
        )
    )
    return int(result.scalar_one())


# ----------------------------------------------------------------
# DRUG — READ
# ----------------------------------------------------------------

async def get_drug(
    db: AsyncSession, hospital_id: uuid.UUID, drug_id: uuid.UUID
) -> Drug:
    """Return one drug with its current total non-expired stock attached
    as `total_active_stock`."""
    drug = await _load_drug(db, hospital_id, drug_id)
    drug.total_active_stock = await _total_active_stock(db, hospital_id, drug_id)
    return drug


async def list_drugs(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    q: Optional[str] = None,
    form: Optional[str] = None,
    include_inactive: bool = False,
) -> dict:
    """
    Paginated drug catalogue, scoped to this hospital, ordered by name.

    Filters: q (ILIKE substring on name + generic_name), form (exact).
    Inactive drugs are excluded unless include_inactive is True.
    """
    conditions = [Drug.hospital_id == hospital_id]
    if not include_inactive:
        conditions.append(Drug.is_active.is_(True))
    if q:
        q_term = f"%{q.strip()}%"
        if q_term != "%%":
            conditions.append(
                or_(
                    Drug.name.ilike(q_term),
                    Drug.generic_name.ilike(q_term),
                )
            )
    if form:
        conditions.append(Drug.form == form)

    stmt = select(Drug).where(*conditions).order_by(Drug.name.asc())
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# DRUG — CREATE / UPDATE / DEACTIVATE
# ----------------------------------------------------------------

async def create_drug(
    db: AsyncSession, hospital_id: uuid.UUID, payload: DrugCreate
) -> Drug:
    """Add a drug to the hospital catalogue."""
    drug = Drug(hospital_id=hospital_id, **payload.model_dump())
    db.add(drug)
    await db.commit()
    await db.refresh(drug)
    logger.info(
        "Drug created",
        extra={"hospital_id": str(hospital_id), "drug_id": str(drug.id)},
    )
    return drug


async def update_drug(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    drug_id: uuid.UUID,
    payload: DrugUpdate,
) -> Drug:
    """Partial update of a catalogue drug."""
    drug = await _load_drug(db, hospital_id, drug_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(drug, field, value)
    await db.commit()
    await db.refresh(drug)
    logger.info(
        "Drug updated",
        extra={"hospital_id": str(hospital_id), "drug_id": str(drug_id)},
    )
    return drug


async def deactivate_drug(
    db: AsyncSession, hospital_id: uuid.UUID, drug_id: uuid.UUID
) -> None:
    """Soft-delete a drug — set is_active=false. The row remains so
    existing prescriptions and batches stay usable."""
    drug = await _load_drug(db, hospital_id, drug_id)
    drug.is_active = False
    await db.commit()
    logger.info(
        "Drug deactivated",
        extra={"hospital_id": str(hospital_id), "drug_id": str(drug_id)},
    )


# ----------------------------------------------------------------
# DRUG BATCHES (sub-resource)
# ----------------------------------------------------------------

async def add_batch(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    drug_id: uuid.UUID,
    payload: BatchCreate,
) -> DrugBatch:
    """Receive a new physical stock batch for a drug."""
    await _load_drug(db, hospital_id, drug_id)
    batch = DrugBatch(
        drug_id=drug_id,
        hospital_id=hospital_id,
        **payload.model_dump(),
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    logger.info(
        "Drug batch received",
        extra={
            "hospital_id": str(hospital_id),
            "drug_id": str(drug_id),
            "batch_id": str(batch.id),
        },
    )
    return batch


async def list_batches(
    db: AsyncSession, hospital_id: uuid.UUID, drug_id: uuid.UUID
) -> list[DrugBatch]:
    """Return a drug's batches ordered by expiry_date (earliest first)."""
    await _load_drug(db, hospital_id, drug_id)
    result = await db.execute(
        select(DrugBatch)
        .where(
            DrugBatch.drug_id == drug_id,
            DrugBatch.hospital_id == hospital_id,
        )
        .order_by(DrugBatch.expiry_date.asc())
    )
    return list(result.scalars().all())


async def update_batch(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    drug_id: uuid.UUID,
    batch_id: uuid.UUID,
    payload: BatchUpdate,
) -> DrugBatch:
    """Partial update of a batch — receiving corrections."""
    await _load_drug(db, hospital_id, drug_id)
    batch = await _load_batch(db, hospital_id, drug_id, batch_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(batch, field, value)
    await db.commit()
    await db.refresh(batch)
    logger.info(
        "Drug batch updated",
        extra={
            "hospital_id": str(hospital_id),
            "drug_id": str(drug_id),
            "batch_id": str(batch_id),
        },
    )
    return batch


async def delete_batch(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    drug_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> None:
    """Hard-delete a batch — drug_batches has no deleted_at column."""
    await _load_drug(db, hospital_id, drug_id)
    batch = await _load_batch(db, hospital_id, drug_id, batch_id)
    await db.delete(batch)
    await db.commit()
    logger.info(
        "Drug batch deleted",
        extra={
            "hospital_id": str(hospital_id),
            "drug_id": str(drug_id),
            "batch_id": str(batch_id),
        },
    )


# ----------------------------------------------------------------
# STOCK QUERIES
# ----------------------------------------------------------------

async def get_stock(
    db: AsyncSession, hospital_id: uuid.UUID, drug_id: uuid.UUID
) -> dict:
    """
    Return a drug's stock breakdown: total non-expired stock, a
    per-batch listing with expiry flags, and the near-expiry count.
    """
    await _load_drug(db, hospital_id, drug_id)
    today = _today()
    near_cutoff = today + timedelta(days=NEAR_EXPIRY_DAYS)

    result = await db.execute(
        select(DrugBatch)
        .where(
            DrugBatch.drug_id == drug_id,
            DrugBatch.hospital_id == hospital_id,
        )
        .order_by(DrugBatch.expiry_date.asc())
    )
    batches = result.scalars().all()

    breakdown = []
    total_active = 0
    near_expiry_count = 0
    for b in batches:
        is_expired = b.expiry_date <= today
        is_near = (not is_expired) and b.expiry_date <= near_cutoff
        if not is_expired:
            total_active += b.stock_quantity
        if is_near:
            near_expiry_count += 1
        breakdown.append(
            {
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "expiry_date": b.expiry_date,
                "stock_quantity": b.stock_quantity,
                "is_expired": is_expired,
                "is_near_expiry": is_near,
            }
        )

    return {
        "drug_id": drug_id,
        "total_active_stock": total_active,
        "near_expiry_count": near_expiry_count,
        "batches": breakdown,
    }


async def low_stock_report(
    db: AsyncSession, hospital_id: uuid.UUID, threshold: int
) -> list[dict]:
    """
    Return active drugs whose total non-expired stock is below
    `threshold` — a pharmacy reorder report. Ordered by stock ascending
    (most urgent first).
    """
    active_stock = func.coalesce(
        func.sum(DrugBatch.stock_quantity).filter(
            DrugBatch.expiry_date > _today()
        ),
        0,
    )
    result = await db.execute(
        select(Drug.id, Drug.name, Drug.generic_name, active_stock.label("stock"))
        .select_from(Drug)
        .outerjoin(DrugBatch, DrugBatch.drug_id == Drug.id)
        .where(Drug.hospital_id == hospital_id, Drug.is_active.is_(True))
        .group_by(Drug.id, Drug.name, Drug.generic_name)
        .having(active_stock < threshold)
        .order_by(active_stock.asc())
    )
    return [
        {
            "drug_id": row[0],
            "name": row[1],
            "generic_name": row[2],
            "total_active_stock": int(row[3]),
        }
        for row in result.all()
    ]

# ================================================================
# NexusCare — app/routers/drugs.py
# Drug catalogue + batch inventory routes, plus the inventory
# low-stock report. Two routers are exported:
#   * router           — /api/v1/drugs   (catalogue, batches, stock)
#   * inventory_router — /api/v1/inventory (low-stock reorder report)
#
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
#
# Authorization: v1 grants drug/inventory access to all hospital
# members. Role-based restrictions are a v2 enhancement.
# ================================================================

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.user import User
from app.schemas.drug import (
    BatchCreate,
    BatchResponse,
    BatchUpdate,
    DrugCreate,
    DrugDetailResponse,
    DrugListResponse,
    DrugResponse,
    DrugUpdate,
    LowStockItem,
    StockResponse,
)
from app.services import drug as drug_service
from app.utils.pagination import Pagination


router = APIRouter(prefix="/api/v1/drugs", tags=["Drugs"])
inventory_router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])


# ----------------------------------------------------------------
# DRUG CATALOGUE
# ----------------------------------------------------------------

@router.post("", response_model=DrugResponse, status_code=status.HTTP_201_CREATED)
async def create_drug(
    payload: DrugCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Add a drug to the hospital catalogue."""
    return await drug_service.create_drug(db, hospital_id, payload)


@router.get("", response_model=DrugListResponse)
async def list_drugs(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    q: Optional[str] = Query(
        default=None, description="Substring match on name + generic_name"
    ),
    form: Optional[str] = Query(default=None, description="Exact match on form"),
    include_inactive: bool = Query(
        default=False, description="Include deactivated drugs"
    ),
):
    """Paginated drug catalogue, ordered by name."""
    return await drug_service.list_drugs(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        q=q,
        form=form,
        include_inactive=include_inactive,
    )


@router.get("/{drug_id}", response_model=DrugDetailResponse)
async def get_drug(
    drug_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one drug with its current total non-expired stock."""
    return await drug_service.get_drug(db, hospital_id, drug_id)


@router.patch("/{drug_id}", response_model=DrugResponse)
async def update_drug(
    drug_id: uuid.UUID,
    payload: DrugUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Partial update of a catalogue drug."""
    return await drug_service.update_drug(db, hospital_id, drug_id, payload)


@router.delete("/{drug_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_drug(
    drug_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Deactivate a drug — set is_active=false. The row remains so
    existing prescriptions and batches stay usable."""
    await drug_service.deactivate_drug(db, hospital_id, drug_id)


# ----------------------------------------------------------------
# DRUG BATCHES (sub-resource)
# ----------------------------------------------------------------

@router.post(
    "/{drug_id}/batches",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_batch(
    drug_id: uuid.UUID,
    payload: BatchCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Receive a new physical stock batch for a drug."""
    return await drug_service.add_batch(db, hospital_id, drug_id, payload)


@router.get("/{drug_id}/batches", response_model=list[BatchResponse])
async def list_batches(
    drug_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """List a drug's batches, ordered by expiry_date (earliest first)."""
    return await drug_service.list_batches(db, hospital_id, drug_id)


@router.patch("/{drug_id}/batches/{batch_id}", response_model=BatchResponse)
async def update_batch(
    drug_id: uuid.UUID,
    batch_id: uuid.UUID,
    payload: BatchUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Partial update of a batch — receiving corrections."""
    return await drug_service.update_batch(
        db, hospital_id, drug_id, batch_id, payload
    )


@router.delete(
    "/{drug_id}/batches/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_batch(
    drug_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Hard-delete a batch — drug_batches has no deleted_at column."""
    await drug_service.delete_batch(db, hospital_id, drug_id, batch_id)


# ----------------------------------------------------------------
# STOCK QUERY
# ----------------------------------------------------------------

@router.get("/{drug_id}/stock", response_model=StockResponse)
async def get_stock(
    drug_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Stock breakdown for a drug: total non-expired stock, per-batch
    listing with expiry flags, and the near-expiry count."""
    return await drug_service.get_stock(db, hospital_id, drug_id)


# ----------------------------------------------------------------
# INVENTORY — low-stock reorder report
# ----------------------------------------------------------------

@inventory_router.get("/low-stock", response_model=list[LowStockItem])
async def low_stock_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    threshold: int = Query(
        default=10, ge=0, description="Flag drugs with non-expired stock below this"
    ),
):
    """Active drugs whose total non-expired stock is below `threshold`,
    ordered by stock ascending (most urgent first)."""
    return await drug_service.low_stock_report(db, hospital_id, threshold)

# ================================================================
# NexusCare — app/schemas/drug.py
# Pydantic v2 schemas for the drug catalogue + batch inventory module:
#   * Drug CRUD + listing
#   * Drug batches (sub-resource of a drug)
#   * Stock query + low-stock report
#
# hospital_id is NEVER accepted from the request body — it comes from
# the JWT. `form` is a free-text string (the schema has no CHECK on it).
# ================================================================

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------
# DRUG
# ----------------------------------------------------------------

class DrugBase(BaseModel):
    """Shared drug catalogue fields."""

    name: str
    generic_name: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[Decimal] = None


class DrugCreate(DrugBase):
    """Body for POST /api/v1/drugs."""


class DrugUpdate(BaseModel):
    """Body for PATCH /api/v1/drugs/{id}. All fields optional."""

    name: Optional[str] = None
    generic_name: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[Decimal] = None
    is_active: Optional[bool] = None


class DrugResponse(DrugBase):
    """Flat drug shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DrugDetailResponse(DrugResponse):
    """Drug with its current total non-expired stock. Returned by
    GET /api/v1/drugs/{id}."""

    total_active_stock: int


# ----------------------------------------------------------------
# DRUG BATCH
# ----------------------------------------------------------------

class BatchBase(BaseModel):
    """Shared drug-batch fields."""

    batch_number: str
    expiry_date: date
    stock_quantity: int = Field(ge=0)
    supplier_name: Optional[str] = None
    purchase_date: Optional[date] = None


class BatchCreate(BatchBase):
    """Body for POST /api/v1/drugs/{drug_id}/batches."""


class BatchUpdate(BaseModel):
    """Body for PATCH /api/v1/drugs/{drug_id}/batches/{id}. All fields
    optional — used for receiving corrections (supplier, expiry, count)."""

    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    supplier_name: Optional[str] = None
    purchase_date: Optional[date] = None


class BatchResponse(BatchBase):
    """Flat batch shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    drug_id: UUID
    hospital_id: UUID
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# STOCK QUERY / LOW-STOCK REPORT
# ----------------------------------------------------------------

class BatchStockItem(BaseModel):
    """One batch line in a drug's stock breakdown."""

    batch_id: UUID
    batch_number: str
    expiry_date: date
    stock_quantity: int
    is_expired: bool
    is_near_expiry: bool


class StockResponse(BaseModel):
    """Stock breakdown for a single drug. total_active_stock sums only
    non-expired batches; near_expiry flags batches expiring within
    30 days."""

    drug_id: UUID
    total_active_stock: int
    near_expiry_count: int
    batches: list[BatchStockItem]


class LowStockItem(BaseModel):
    """One drug below the requested stock threshold (reorder report)."""

    drug_id: UUID
    name: str
    generic_name: Optional[str] = None
    total_active_stock: int


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

DrugListResponse = PagedResponse[DrugResponse]

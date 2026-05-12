# ================================================================
# NexusCare — utils/pagination.py
# FastAPI pagination dependency, generic response schema,
# and async paginate() helper for SQLAlchemy 2.0 queries.
# ================================================================

import math
from typing import Any, Generic, Optional, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar("T")


# ----------------------------------------------------------------
# DEPENDENCY
# ----------------------------------------------------------------

class Pagination:
    """
    FastAPI Depends-compatible query-param dependency.
    Usage: pagination: Pagination = Depends(Pagination)
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    ) -> None:
        self.page = page
        self.size = size


# ----------------------------------------------------------------
# RESPONSE SCHEMA
# ----------------------------------------------------------------

class PagedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper returned by list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    page: int
    size: int
    pages: int


# ----------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------

async def paginate(
    db: AsyncSession,
    query: Select,
    page: int,
    size: int,
) -> tuple[Sequence[Any], int]:
    """
    Runs a COUNT subquery then fetches one page of results.
    Returns (items, total) — pass both to make_paged_response().
    """
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total: int = count_result.scalar_one()

    result = await db.execute(query.limit(size).offset((page - 1) * size))
    items = result.scalars().all()

    return items, total


def make_paged_response(
    items: Sequence[Any],
    total: int,
    page: int,
    size: int,
) -> dict:
    """Assembles the PagedResponse dict from paginate() output."""
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if total > 0 else 1,
    }

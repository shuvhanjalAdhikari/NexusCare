# ================================================================
# NexusCare — app/routers/billing.py
# Billing reports: outstanding invoices and a revenue summary.
# All under /api/v1/billing.
#
# Every route runs under get_current_user + get_hospital_id;
# results are hospital-scoped (CLAUDE.md §13).
# ================================================================

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.user import User
from app.schemas.invoice import InvoiceResponse, RevenueReportResponse
from app.services import invoice as invoice_service
from app.services import payment as payment_service


router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


@router.get("/outstanding", response_model=list[InvoiceResponse])
async def list_outstanding(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Invoices with a positive balance_due — money still owed.
    Includes any 'paid' invoice whose balance went positive after a
    refund."""
    return await invoice_service.list_outstanding(db, hospital_id)


@router.get("/revenue", response_model=RevenueReportResponse)
async def revenue_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    from_date: Annotated[date, Query(description="Start of range (inclusive)")],
    to_date: Annotated[date, Query(description="End of range (inclusive)")],
):
    """Revenue over a date range: gross payments, refunds, and net."""
    return await payment_service.revenue_report(
        db, hospital_id, from_date, to_date
    )

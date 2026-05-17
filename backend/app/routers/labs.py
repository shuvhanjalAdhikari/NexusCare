# ================================================================
# NexusCare — app/routers/labs.py
# Diagnostic lab workflow routes. Three routers are exported:
#   * lab_tests_router       — /api/v1/lab-tests        (catalogue CRUD)
#   * router                 — /api/v1/lab-orders       (orders + the
#                              one-to-one nested /result sub-resource)
#   * visit_lab_orders_router — /api/v1/visits/{visit_id}/lab-orders
#                              (nested order creation only)
#
# A lab order is created under a visit; patient_id / doctor_id are
# taken from that visit. Listing, retrieval, status changes, and the
# result sub-resource all live under /api/v1/lab-orders.
#
# Every route runs under get_current_user + get_hospital_id;
# cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
#
# Authorization: v1 grants lab access to all hospital members.
# Role-based restrictions are a v2 enhancement.
# ================================================================

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import LabOrderStatus
from app.database import get_db
from app.dependencies.auth import get_current_membership, get_current_user
from app.dependencies.hospital import get_hospital_id
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.lab import (
    LabOrderCreate,
    LabOrderDetailResponse,
    LabOrderListResponse,
    LabOrderResponse,
    LabOrderUpdate,
    LabResultCreate,
    LabResultResponse,
    LabResultUpdate,
    LabTestCreate,
    LabTestResponse,
    LabTestUpdate,
)
from app.services import lab as lab_service
from app.utils.pagination import Pagination


lab_tests_router = APIRouter(prefix="/api/v1/lab-tests", tags=["Lab"])
router = APIRouter(prefix="/api/v1/lab-orders", tags=["Lab"])
visit_lab_orders_router = APIRouter(prefix="/api/v1/visits", tags=["Lab"])


# ================================================================
# LAB-TEST CATALOGUE
# ================================================================

@lab_tests_router.post(
    "", response_model=LabTestResponse, status_code=status.HTTP_201_CREATED
)
async def create_lab_test(
    payload: LabTestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Create a lab-test catalogue entry for this hospital."""
    return await lab_service.create_lab_test(db, hospital_id, payload)


@lab_tests_router.get("", response_model=list[LabTestResponse])
async def list_lab_tests(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    q: Optional[str] = Query(default=None, description="Name substring filter"),
    is_active: Optional[bool] = Query(
        default=None, description="Filter by active status"
    ),
):
    """List this hospital's lab-test catalogue, ordered by name."""
    return await lab_service.list_lab_tests(
        db, hospital_id, q=q, is_active=is_active
    )


@lab_tests_router.get("/{test_id}", response_model=LabTestResponse)
async def get_lab_test(
    test_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one lab-test catalogue entry."""
    return await lab_service.get_lab_test(db, hospital_id, test_id)


@lab_tests_router.patch("/{test_id}", response_model=LabTestResponse)
async def update_lab_test(
    test_id: uuid.UUID,
    payload: LabTestUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Partial update of a lab-test catalogue entry. Setting
    is_active=false deactivates it (lab tests are never deleted)."""
    return await lab_service.update_lab_test(db, hospital_id, test_id, payload)


# ================================================================
# LAB ORDER — nested create under a visit
# ================================================================

@visit_lab_orders_router.post(
    "/{visit_id}/lab-orders",
    response_model=LabOrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lab_order(
    visit_id: uuid.UUID,
    payload: LabOrderCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Order a diagnostic test during a visit. The order opens in
    status 'ordered'; patient_id / doctor_id are taken from the visit."""
    return await lab_service.create_lab_order(
        db,
        hospital_id,
        visit_id,
        payload,
        created_by=current_user.id,
        created_by_membership_id=membership.id,
    )


# ================================================================
# LAB ORDER — read / update / delete
# ================================================================

@router.get("", response_model=LabOrderListResponse)
async def list_lab_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[Pagination, Depends(Pagination)],
    lab_order_status: Optional[LabOrderStatus] = Query(
        default=None, alias="status", description="Filter by order status"
    ),
    doctor_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by ordering doctor"
    ),
    patient_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by patient"
    ),
    visit_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by visit"
    ),
    date_from: Optional[date] = Query(
        default=None, description="Earliest order date (inclusive)"
    ),
    date_to: Optional[date] = Query(
        default=None, description="Latest order date (inclusive)"
    ),
):
    """Paginated lab-order list, ordered by created_at descending."""
    return await lab_service.list_lab_orders(
        db,
        hospital_id,
        pagination.page,
        pagination.size,
        status=lab_order_status.value if lab_order_status else None,
        doctor_id=doctor_id,
        patient_id=patient_id,
        visit_id=visit_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{order_id}", response_model=LabOrderDetailResponse)
async def get_lab_order(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get one lab order with its nested test catalogue entry and result."""
    return await lab_service.get_lab_order(db, hospital_id, order_id)


@router.patch("/{order_id}", response_model=LabOrderDetailResponse)
async def update_lab_order(
    order_id: uuid.UUID,
    payload: LabOrderUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Move a lab order along its state machine. Entering 'reviewed'
    stamps the result's reviewed_by / reviewed_at — the doctor's
    sign-off."""
    return await lab_service.update_lab_order(
        db,
        hospital_id,
        order_id,
        payload,
        reviewed_by=current_user.id,
        reviewed_by_membership_id=membership.id,
    )


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lab_order(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Hard-delete a lab order — only while still in status 'ordered'."""
    await lab_service.delete_lab_order(db, hospital_id, order_id)


# ================================================================
# LAB RESULT — one-to-one sub-resource of a lab order
# ================================================================

@router.post(
    "/{order_id}/result",
    response_model=LabResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lab_result(
    order_id: uuid.UUID,
    payload: LabResultCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
):
    """Record the result for a lab order. The order must be
    'in_progress'; an order has at most one result."""
    return await lab_service.create_lab_result(
        db,
        hospital_id,
        order_id,
        payload,
        uploaded_by=current_user.id,
        uploaded_by_membership_id=membership.id,
    )


@router.get("/{order_id}/result", response_model=LabResultResponse)
async def get_lab_result(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Get the result for a lab order."""
    return await lab_service.get_lab_result(db, hospital_id, order_id)


@router.patch("/{order_id}/result", response_model=LabResultResponse)
async def update_lab_result(
    order_id: uuid.UUID,
    payload: LabResultUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Correct a lab result. Permitted while the order is 'in_progress'
    or 'result_ready'; uploaded_by stays the original lab technician."""
    return await lab_service.update_lab_result(db, hospital_id, order_id, payload)


@router.delete(
    "/{order_id}/result", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_lab_result(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    hospital_id: Annotated[uuid.UUID, Depends(get_hospital_id)],
    _: Annotated[User, Depends(get_current_user)],
):
    """Hard-delete a lab result — only while 'in_progress' or
    'result_ready'."""
    await lab_service.delete_lab_result(db, hospital_id, order_id)

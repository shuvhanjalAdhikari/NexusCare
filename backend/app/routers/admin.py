# ================================================================
# NexusCare — app/routers/admin.py
# Platform-admin (super-admin) routes. Every route in this file is
# gated by require_super_admin. Tenant isolation (hospital_id from
# the JWT) does NOT apply here — this prefix is the one exception
# documented in CLAUDE.md §13.
# ================================================================

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_super_admin
from app.models.user import User
from app.schemas.admin import (
    HospitalCreateRequest,
    HospitalCreateResponse,
    HospitalSummary,
)
from app.services import admin as admin_service


router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(require_super_admin)],
)


# ----------------------------------------------------------------
# CREATE HOSPITAL
# ----------------------------------------------------------------

@router.post(
    "/hospitals",
    response_model=HospitalCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_hospital(
    payload: HospitalCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_super_admin)],
):
    hospital, admin, invite_token, expires_at = (
        await admin_service.create_hospital_with_admin(db, payload)
    )
    return HospitalCreateResponse(
        hospital=HospitalSummary.model_validate(hospital),
        admin_user_id=admin.id,
        admin_email=admin.email,
        invite_token=invite_token,
        invite_expires_at=expires_at,
    )

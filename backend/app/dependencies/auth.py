# ================================================================
# NexusCare — app/dependencies/auth.py
# JWT-backed FastAPI dependencies. Every protected route depends on
# get_current_user (validates type=="access") at minimum; tenant
# routes also depend on get_current_membership / get_hospital_id.
# ================================================================

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import UserRole
from app.database import get_db
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.auth import SelectionTokenPayload
from app.services.auth import TOKEN_TYPE_ACCESS, TOKEN_TYPE_SELECTION
from app.utils.exceptions import (
    ForbiddenError,
    InactiveUserError,
    SelectionTokenRequiredError,
    UnauthorizedError,
)
from app.utils.security import decode_token


# tokenUrl points at /login-form, which accepts OAuth2 form-encoded
# credentials so Swagger UI's Authorize button works end-to-end.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login-form", auto_error=False)


# ----------------------------------------------------------------
# CURRENT USER
# ----------------------------------------------------------------

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Resolve the access-token bearer to a live, active User.

    Selection tokens (type=="selection") are rejected here — only
    /auth/select-workspace decodes those, inline.
    """
    if not token:
        raise UnauthorizedError()

    payload = decode_token(token)

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise SelectionTokenRequiredError()

    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError()

    try:
        user_id = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise UnauthorizedError()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.deleted_at is not None or not user.is_active:
        raise InactiveUserError()

    return user


# ----------------------------------------------------------------
# CURRENT MEMBERSHIP — re-validates on every request
# ----------------------------------------------------------------

async def get_current_membership(
    token: Annotated[str, Depends(oauth2_scheme)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HospitalMembership:
    """
    Reload the membership row referenced in the JWT and confirm it is
    still usable (active, not deleted, still owned by this user, role
    eagerly loaded for downstream consumers). Hospital-level checks
    live in get_hospital_id so super-admin paths can opt out of them.
    """
    payload = decode_token(token)

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise SelectionTokenRequiredError()

    membership_claim = payload.get("membership_id")
    if not membership_claim:
        raise UnauthorizedError()

    try:
        membership_id = uuid.UUID(membership_claim)
    except (ValueError, TypeError):
        raise UnauthorizedError()

    result = await db.execute(
        select(HospitalMembership)
        .options(
            selectinload(HospitalMembership.hospital),
            selectinload(HospitalMembership.role),
        )
        .where(HospitalMembership.id == membership_id)
    )
    membership = result.scalar_one_or_none()

    if (
        membership is None
        or membership.deleted_at is not None
        or not membership.is_active
        or membership.user_id != current_user.id
    ):
        raise UnauthorizedError()

    return membership


# ----------------------------------------------------------------
# ROLE GUARDS
# ----------------------------------------------------------------

def require_role(*roles: UserRole):
    """
    Dependency factory: only allow callers whose JWT role claim matches
    one of the supplied roles. Re-checks against the live membership row
    so a role rename or revocation takes effect on the next request.
    """
    allowed = {r.value for r in roles}

    async def _guard(
        membership: Annotated[HospitalMembership, Depends(get_current_membership)],
    ) -> HospitalMembership:
        if membership.role.name not in allowed:
            raise ForbiddenError()
        return membership

    return _guard


async def get_selection_token(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> SelectionTokenPayload:
    """
    Decode a Bearer-delivered selection token and enforce type=="selection".

    Returned to /auth/select-workspace so it can mint the scoped access
    token without ever needing the raw selection token in the body.
    Access tokens presented here surface the same generic error as
    malformed selection tokens to keep the failure modes indistinguishable.
    """
    if not token:
        raise UnauthorizedError()

    payload = decode_token(token)

    if payload.get("type") != TOKEN_TYPE_SELECTION:
        raise SelectionTokenRequiredError()

    try:
        return SelectionTokenPayload(**payload)
    except (TypeError, ValueError):
        raise UnauthorizedError()


async def require_super_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Platform admin guard. Does not require a hospital-scoped token."""
    if current_user.system_role != UserRole.SUPER_ADMIN.value:
        raise ForbiddenError()
    return current_user

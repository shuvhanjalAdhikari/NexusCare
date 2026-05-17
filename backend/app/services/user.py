# ================================================================
# NexusCare — app/services/user.py
# Hospital-scoped user management:
#   * Invite (handles "new user" + "existing user, new hospital")
#   * List / get
#   * Profile update (self and admin)
#   * Membership update (role / activation)
#   * Soft-delete a membership
#
# Tenant rule (CLAUDE.md §13): every query filters by hospital_id
# from the JWT. Cross-tenant access surfaces as NotFoundError, never
# ForbiddenError — never leak existence across tenants.
#
# A hospital admin CANNOT silently rewrite another user's password.
# They can deactivate the membership, change the role, or initiate a
# fresh invite, but the only way a user's password changes is:
#   * self-service via /auth/change-password (knows current password)
#   * self-service via /auth/reset-password   (knows a reset token)
#   * /auth/accept-invite                     (knows an invite token)
# ================================================================

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import UserRole
from app.models.hospital import Role
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.audit import RequestMetadata
from app.schemas.user import (
    MembershipUpdateRequest,
    UserInviteRequest,
    UserListItem,
    UserSelfUpdateRequest,
    UserUpdateRequest,
)
from app.services import audit as audit_service
from app.services.auth import issue_invite_token
from app.utils.email import normalize_email
from app.utils.exceptions import (
    BadRequestError,
    EmailAlreadyInHospitalError,
    NotFoundError,
)
from app.utils.pagination import make_paged_response
from app.utils.security import hash_password

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# INTERNAL HELPERS
# ----------------------------------------------------------------

async def _get_role_for_hospital(
    db: AsyncSession, hospital_id: uuid.UUID, role_id: uuid.UUID
) -> Role:
    """
    Load a role and verify it is usable for this hospital. Hospitals can
    use roles they own (hospital_id == this) OR system roles (hospital_id IS NULL).
    Anything else is a NotFoundError (cross-tenant leakage prevention).
    """
    result = await db.execute(
        select(Role).where(
            Role.id == role_id,
            or_(Role.hospital_id == hospital_id, Role.hospital_id.is_(None)),
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role", role_id)
    return role


async def _membership_in_hospital(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> Optional[HospitalMembership]:
    """Returns the membership row that links this user to this hospital, if any."""
    stmt = (
        select(HospitalMembership)
        .options(
            selectinload(HospitalMembership.role),
            selectinload(HospitalMembership.user),
        )
        .where(
            HospitalMembership.hospital_id == hospital_id,
            HospitalMembership.user_id == user_id,
        )
    )
    if not include_deleted:
        stmt = stmt.where(HospitalMembership.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _count_active_admins(
    db: AsyncSession, hospital_id: uuid.UUID
) -> int:
    """How many active, non-deleted hospital_admin memberships exist in this hospital."""
    stmt = (
        select(func.count(HospitalMembership.id))
        .join(HospitalMembership.role)
        .where(
            HospitalMembership.hospital_id == hospital_id,
            HospitalMembership.is_active.is_(True),
            HospitalMembership.deleted_at.is_(None),
            Role.name == UserRole.HOSPITAL_ADMIN.value,
        )
    )
    result = await db.execute(stmt)
    return int(result.scalar_one())


# ----------------------------------------------------------------
# INVITE
# ----------------------------------------------------------------

async def invite_user_to_hospital(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    payload: UserInviteRequest,
    inviter_user_id: uuid.UUID,
) -> dict:
    """
    Two paths, picked by whether the normalized email already exists in users:

      * New email → create User (is_active=False, throwaway password) + create
        HospitalMembership + return a 7-day invite token. The user must call
        /auth/accept-invite to set a password before they can log in.

      * Existing email → no invite token is issued. The user already has a
        usable password; we just create (or reactivate) a HospitalMembership
        for this hospital so they can log in to it via the normal flow.

    Cross-tenant leakage note: the two response shapes differ
    (invite_token set vs null), so a hospital admin can in principle enumerate
    which emails already exist as platform users by repeatedly inviting. This
    is an accepted minor info leak — the caller must already be an authenticated
    admin within their own hospital, and the leak does not cross tenant
    boundaries (it tells you whether the email is on the platform, not what
    hospitals they belong to). A future hardening could equalize responses
    entirely (always return "an invitation has been sent") but the current
    shape is more useful operationally.
    """
    role = await _get_role_for_hospital(db, hospital_id, payload.role_id)

    normalized_email = normalize_email(payload.email)
    result = await db.execute(
        select(User).where(User.email == normalized_email)
    )
    existing_user = result.scalar_one_or_none()

    # ---------- EXISTING USER PATH ----------
    if existing_user is not None and existing_user.deleted_at is None:
        existing_membership = await _membership_in_hospital(
            db, hospital_id, existing_user.id, include_deleted=True
        )
        if existing_membership is not None:
            if (
                existing_membership.deleted_at is None
                and existing_membership.is_active
            ):
                raise EmailAlreadyInHospitalError()
            # Reactivate the soft-deleted / suspended membership.
            existing_membership.deleted_at = None
            existing_membership.is_active = True
            existing_membership.role_id = role.id
            existing_membership.invited_by = inviter_user_id
            await db.commit()
            logger.info(
                "Existing user re-added to hospital",
                extra={
                    "hospital_id": str(hospital_id),
                    "user_id": str(existing_user.id),
                },
            )
        else:
            new_membership = HospitalMembership(
                user_id=existing_user.id,
                hospital_id=hospital_id,
                role_id=role.id,
                is_active=True,
                invited_by=inviter_user_id,
            )
            db.add(new_membership)
            await db.commit()
            logger.info(
                "Existing user added to hospital",
                extra={
                    "hospital_id": str(hospital_id),
                    "user_id": str(existing_user.id),
                },
            )

        return {
            "user_id": existing_user.id,
            "email": existing_user.email,
            "invite_token": None,
            "expires_at": None,
            "requires_password": False,
            "message": "User is already on the platform; they can sign in with their existing password.",
        }

    # ---------- NEW USER PATH ----------
    try:
        new_user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=normalized_email,
            password_hash=hash_password(uuid.uuid4().hex),
            is_active=False,
        )
        db.add(new_user)
        await db.flush()

        new_membership = HospitalMembership(
            user_id=new_user.id,
            hospital_id=hospital_id,
            role_id=role.id,
            is_active=True,
            invited_by=inviter_user_id,
        )
        db.add(new_membership)
        await db.flush()

        invite_token, expires_at = issue_invite_token(
            new_user.id, new_membership.id, new_user.email
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(new_user)
    logger.info(
        "New user invited",
        extra={
            "hospital_id": str(hospital_id),
            "user_id": str(new_user.id),
        },
    )
    return {
        "user_id": new_user.id,
        "email": new_user.email,
        "invite_token": invite_token,
        "expires_at": expires_at,
        "requires_password": True,
        "message": "Invitation issued. Share the invite token with the user; they must call /auth/accept-invite to set a password.",
    }


# ----------------------------------------------------------------
# LIST / GET
# ----------------------------------------------------------------

async def list_users(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    role_filter: Optional[str] = None,
) -> dict:
    """
    Paginated list of users with an active membership in this hospital.
    Returns rows shaped for UserListItem (user fields + role name +
    membership_active + joined_at).
    """
    conditions = [
        HospitalMembership.hospital_id == hospital_id,
        HospitalMembership.deleted_at.is_(None),
        User.deleted_at.is_(None),
    ]
    if role_filter is not None:
        conditions.append(Role.name == role_filter)

    base_stmt = (
        select(
            User.id.label("id"),
            User.email.label("email"),
            User.first_name.label("first_name"),
            User.last_name.label("last_name"),
            Role.name.label("role"),
            User.is_active.label("is_active"),
            HospitalMembership.is_active.label("membership_active"),
            HospitalMembership.created_at.label("joined_at"),
        )
        .join(HospitalMembership, HospitalMembership.user_id == User.id)
        .join(Role, Role.id == HospitalMembership.role_id)
        .where(and_(*conditions))
        .order_by(User.first_name.asc(), User.last_name.asc())
    )

    count_stmt = (
        select(func.count())
        .select_from(
            select(User.id)
            .join(HospitalMembership, HospitalMembership.user_id == User.id)
            .join(Role, Role.id == HospitalMembership.role_id)
            .where(and_(*conditions))
            .subquery()
        )
    )
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar_one())

    page_stmt = base_stmt.limit(size).offset((page - 1) * size)
    page_result = await db.execute(page_stmt)
    rows = page_result.mappings().all()
    items = [UserListItem(**row) for row in rows]

    return make_paged_response(items=items, total=total, page=page, size=size)


async def get_user_in_hospital(
    db: AsyncSession, hospital_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    """
    Returns the User iff they have a non-deleted membership in this hospital.
    Returns NotFoundError for cross-tenant access (CLAUDE.md §13).
    """
    membership = await _membership_in_hospital(db, hospital_id, user_id)
    if membership is None or membership.user.deleted_at is not None:
        raise NotFoundError("User", user_id)
    return membership.user


# ----------------------------------------------------------------
# PROFILE UPDATES
# ----------------------------------------------------------------

def _apply_profile_fields(user: User, payload: UserUpdateRequest) -> None:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)


async def update_user_profile(
    db: AsyncSession, user: User, payload: UserSelfUpdateRequest
) -> User:
    """Self-service profile update. Cannot touch role, email, or activation."""
    _apply_profile_fields(user, payload)
    await db.commit()
    await db.refresh(user)
    logger.info("User updated own profile", extra={"user_id": str(user.id)})
    return user


async def update_user_profile_as_admin(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
) -> User:
    """
    Hospital admin updates a user's profile. Verifies the target is a
    member of this hospital before touching anything (cross-tenant
    isolation). Does NOT modify role, password, or activation — those
    have dedicated endpoints.
    """
    user = await get_user_in_hospital(db, hospital_id, user_id)
    _apply_profile_fields(user, payload)
    await db.commit()
    await db.refresh(user)
    logger.info(
        "Admin updated user profile",
        extra={"hospital_id": str(hospital_id), "user_id": str(user.id)},
    )
    return user


# ----------------------------------------------------------------
# MEMBERSHIP UPDATE (role / activation)
# ----------------------------------------------------------------

async def update_membership(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MembershipUpdateRequest,
    acting_user_id: uuid.UUID,
) -> HospitalMembership:
    """
    Change a membership's role and/or active flag.

    Invariants enforced:
      * You cannot deactivate or demote your own membership (use a
        co-admin if you need to step down).
      * The hospital must always have at least one active hospital_admin
        membership. Soft guard — a future DB trigger could harden this
        against concurrent admin removals.
    """
    membership = await _membership_in_hospital(db, hospital_id, user_id)
    if membership is None:
        raise NotFoundError("User", user_id)

    if payload.role_id is None and payload.is_active is None:
        # Nothing to do; surface this loudly rather than silently no-op.
        raise BadRequestError("Specify role_id or is_active.")

    # Self-deactivation / self-demotion guard.
    if user_id == acting_user_id:
        if payload.is_active is False:
            raise BadRequestError("You cannot deactivate your own membership.")
        if (
            payload.role_id is not None
            and membership.role.name == UserRole.HOSPITAL_ADMIN.value
        ):
            new_role = await _get_role_for_hospital(db, hospital_id, payload.role_id)
            if new_role.name != UserRole.HOSPITAL_ADMIN.value:
                raise BadRequestError("You cannot demote your own admin role.")
            # Same admin role, different role row — harmless, fall through.

    # Apply changes.
    if payload.role_id is not None:
        new_role = await _get_role_for_hospital(db, hospital_id, payload.role_id)
        membership.role_id = new_role.id
        # selectinload doesn't refresh after a swap; reset the relationship so
        # downstream code reads the new role.
        membership.role = new_role

    if payload.is_active is not None:
        membership.is_active = payload.is_active

    # Last-admin guard. Flush so the count sees pending changes, then
    # check the proposed state. Soft guard: a future DB trigger could
    # harden this against concurrent admin removals.
    await db.flush()
    if await _count_active_admins(db, hospital_id) == 0:
        await db.rollback()
        raise BadRequestError(
            "This hospital must have at least one active administrator."
        )

    await db.commit()
    await db.refresh(membership)
    logger.info(
        "Membership updated",
        extra={
            "hospital_id": str(hospital_id),
            "user_id": str(user_id),
            "membership_id": str(membership.id),
        },
    )
    return membership


async def soft_delete_membership(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    user_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    acting_membership_id: uuid.UUID,
    request_meta: Optional[RequestMetadata] = None,
) -> None:
    """
    Soft-deletes the user's membership in this hospital. The global User
    row is NOT touched — they may be a member of other hospitals.

    Same self-removal + last-admin invariants as update_membership.

    Audit: a 'deactivate_membership' row is written in the same
    transaction. user_id / membership_id on the audit row identify the
    ADMIN who performed the removal; the affected membership is the
    resource_id.
    """
    membership = await _membership_in_hospital(db, hospital_id, user_id)
    if membership is None:
        raise NotFoundError("User", user_id)

    if user_id == acting_user_id:
        raise BadRequestError("You cannot remove your own membership.")

    if membership.role.name == UserRole.HOSPITAL_ADMIN.value:
        # Pre-check: would removing this admin leave the hospital with zero?
        membership.deleted_at = datetime.now(timezone.utc)
        membership.is_active = False
        await db.flush()
        admin_count = await _count_active_admins(db, hospital_id)
        if admin_count == 0:
            await db.rollback()
            raise BadRequestError(
                "This hospital must have at least one active administrator."
            )
    else:
        membership.deleted_at = datetime.now(timezone.utc)
        membership.is_active = False

    # Audit row rides on the same commit as the soft-delete.
    await audit_service.log_audit(
        db,
        action="deactivate_membership",
        resource_type="membership",
        resource_id=membership.id,
        user_id=acting_user_id,
        hospital_id=hospital_id,
        membership_id=acting_membership_id,
        old_value={"is_active": True},
        new_value={"is_active": False},
        request_meta=request_meta,
    )

    await db.commit()
    logger.info(
        "Membership removed",
        extra={
            "hospital_id": str(hospital_id),
            "user_id": str(user_id),
        },
    )

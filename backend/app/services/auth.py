# ================================================================
# NexusCare — app/services/auth.py
# Authentication and token issuance. Two-step (Slack-style) login.
#
# Access tokens last 480 minutes (config.access_token_expire_minutes)
# and there is no refresh-token flow yet. v2 will add refresh tokens
# so we can shorten the access-token lifetime without forcing daily
# logins.
#
# Brute-force lockout policy:
#   The lockout counter applies ONLY to wrong-password attempts on
#   existing user accounts. Attempts with non-existent emails do NOT
#   increment any counter (the timing-attack defense still runs a
#   dummy bcrypt verify so response time stays uniform). This is
#   intentional — an attacker hammering random emails cannot lock
#   any real account. After LOCKOUT_THRESHOLD consecutive failures
#   the account is locked for LOCKOUT_WINDOW; further attempts during
#   that window do not extend the lock (otherwise an attacker could
#   keep a real user locked out by continuously guessing).
# ================================================================

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.constants.enums import HospitalStatus
from app.models.hospital import Hospital, Role
from app.models.membership import HospitalMembership
from app.models.user import User
from app.utils.exceptions import InvalidCredentialsError
from app.utils.security import (
    create_access_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# TIMING-ATTACK DEFENSE
# ----------------------------------------------------------------
# Pre-computed at import time so a missing user still pays the cost
# of one bcrypt comparison. Keeps login response time roughly equal
# whether the email exists or not, preventing enumeration via timing.
_DUMMY_PASSWORD_HASH = hash_password("dummy_password_to_prevent_timing_attacks")


# ----------------------------------------------------------------
# LOCKOUT POLICY
# ----------------------------------------------------------------
LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


# ----------------------------------------------------------------
# JWT CLAIM TYPES
# ----------------------------------------------------------------

TOKEN_TYPE_SELECTION = "selection"
TOKEN_TYPE_ACCESS = "access"


# ----------------------------------------------------------------
# AUTHENTICATE
# ----------------------------------------------------------------

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """
    Verify credentials. All failure modes raise the same
    InvalidCredentialsError with the same message: wrong email, wrong
    password, soft-deleted user, inactive user, locked account.
    Distinguishing them would leak account state to attackers
    performing user enumeration.
    """
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    # Missing email: pay the bcrypt cost against a dummy hash to equalise
    # timing, then bail. No counter exists for non-existent emails — see
    # the module banner for the rationale.
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        logger.warning("Login failed: unknown email")
        raise InvalidCredentialsError()

    # Always compute the password check, even on a locked account, so an
    # observer cannot distinguish "locked" from "wrong password" by timing.
    password_ok = verify_password(password, user.password_hash)
    now = datetime.now(timezone.utc)

    # Locked window: short-circuit without incrementing. Incrementing here
    # would let an attacker keep a real user locked out indefinitely by
    # hammering the endpoint during the cooldown.
    if user.locked_until is not None and user.locked_until > now:
        logger.warning(
            "Login failed: account locked",
            extra={"user_id": str(user.id)},
        )
        raise InvalidCredentialsError()

    if not password_ok:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= LOCKOUT_THRESHOLD:
            user.locked_until = now + LOCKOUT_WINDOW
        await db.commit()
        logger.warning(
            "Login failed: wrong password",
            extra={"user_id": str(user.id)},
        )
        raise InvalidCredentialsError()

    # Right password but account unreachable. Do not increment the counter:
    # the account can't be unlocked from this path anyway, and we don't want
    # to let an attacker who knows one valid password lock a known-existing
    # but inactive account.
    if user.deleted_at is not None or not user.is_active:
        logger.warning(
            "Login failed: account inactive or deleted",
            extra={"user_id": str(user.id)},
        )
        raise InvalidCredentialsError()

    # Successful credential verification — clear the counter immediately so
    # a user who got their password right after a few typos isn't one bad
    # attempt away from a lockout. select_workspace clears it again as a
    # defensive no-op for the rare path that skips this reset.
    if user.failed_login_attempts != 0 or user.locked_until is not None:
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()

    return user


# ----------------------------------------------------------------
# SELECTION TOKEN — short-lived, no hospital context
# ----------------------------------------------------------------

def issue_selection_token(user: User) -> str:
    """5-minute token that can only call /auth/select-workspace."""
    return create_access_token(
        subject={"sub": str(user.id), "type": TOKEN_TYPE_SELECTION},
        expires_minutes=settings.selection_token_expire_minutes,
    )


# ----------------------------------------------------------------
# LIST MEMBERSHIPS — only active + non-suspended hospitals
# ----------------------------------------------------------------

async def list_memberships(
    db: AsyncSession, user_id: uuid.UUID
) -> list[HospitalMembership]:
    """
    Returns every membership the user can actually use right now:
    active membership, not soft-deleted, and the hospital itself is
    not suspended. Eagerly loads hospital + role for the response.
    """
    result = await db.execute(
        select(HospitalMembership)
        .options(
            selectinload(HospitalMembership.hospital),
            selectinload(HospitalMembership.role),
        )
        .join(HospitalMembership.hospital)
        .where(HospitalMembership.user_id == user_id)
        .where(HospitalMembership.is_active.is_(True))
        .where(HospitalMembership.deleted_at.is_(None))
        .where(Hospital.status != HospitalStatus.SUSPENDED.value)
    )
    return list(result.scalars().all())


# ----------------------------------------------------------------
# ACCESS TOKEN — full scoped JWT for protected routes
# ----------------------------------------------------------------

def issue_access_token(user: User, membership: HospitalMembership) -> "TokenResponse":
    """
    Build the scoped JWT. Caller must have already loaded membership.role
    (e.g. via selectinload) so we can embed role.name without triggering
    a lazy load inside this sync function.
    """
    # Imported here to avoid circular imports with schemas → services.
    from app.schemas.auth import TokenResponse

    token = create_access_token(
        subject={
            "sub": str(user.id),
            "hospital_id": str(membership.hospital_id),
            "membership_id": str(membership.id),
            "role": membership.role.name,
            "type": TOKEN_TYPE_ACCESS,
        },
        expires_minutes=settings.access_token_expire_minutes,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ----------------------------------------------------------------
# SELECT WORKSPACE
# ----------------------------------------------------------------

async def select_workspace(
    db: AsyncSession, user_id: uuid.UUID, hospital_id: uuid.UUID
) -> "TokenResponse":
    """
    Validate the membership is currently usable, then mint an access
    token. Same enumeration-safe error path as authenticate_user:
    membership missing, inactive, soft-deleted, or hospital suspended
    all surface as InvalidCredentialsError.
    """
    result = await db.execute(
        select(HospitalMembership)
        .options(
            selectinload(HospitalMembership.hospital),
            selectinload(HospitalMembership.role),
            selectinload(HospitalMembership.user),
        )
        .join(HospitalMembership.hospital)
        .where(HospitalMembership.user_id == user_id)
        .where(HospitalMembership.hospital_id == hospital_id)
        .where(HospitalMembership.is_active.is_(True))
        .where(HospitalMembership.deleted_at.is_(None))
        .where(Hospital.status != HospitalStatus.SUSPENDED.value)
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        logger.warning(
            "Workspace selection failed",
            extra={"user_id": str(user_id), "hospital_id": str(hospital_id)},
        )
        raise InvalidCredentialsError()

    # Stamp last_login_at on the moment a usable token is issued.
    # Also clear any residual lockout state — authenticate_user normally
    # resets it, but this keeps the invariant true if a future code path
    # ever mints a selection token without going through authenticate_user.
    membership.user.last_login_at = datetime.now(timezone.utc)
    membership.user.failed_login_attempts = 0
    membership.user.locked_until = None
    await db.commit()

    logger.info(
        "Workspace selected",
        extra={
            "hospital_id": str(membership.hospital_id),
            "user_id": str(user_id),
            "membership_id": str(membership.id),
        },
    )
    return issue_access_token(membership.user, membership)


# ----------------------------------------------------------------
# CHANGE PASSWORD
# ----------------------------------------------------------------

async def change_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    """
    Verify the current password, then rotate the hash.

    Existing JWTs remain valid until their natural expiry — there is
    no token revocation list yet. A future phase will add a
    token_version column on users (or a revocation store) so password
    changes can invalidate every outstanding session immediately.
    """
    if not verify_password(current_password, user.password_hash):
        logger.warning(
            "Password change failed: wrong current password",
            extra={"user_id": str(user.id)},
        )
        raise InvalidCredentialsError()

    user.password_hash = hash_password(new_password)
    await db.commit()
    logger.info("Password changed", extra={"user_id": str(user.id)})


# ----------------------------------------------------------------
# RESPONSE BUILDERS
# ----------------------------------------------------------------

def build_membership_options(
    memberships: list[HospitalMembership],
) -> list["MembershipOption"]:
    """
    Flatten loaded membership rows into the schema shape the
    /auth/login response expects.
    """
    from app.schemas.auth import MembershipOption

    return [
        MembershipOption(
            hospital_id=m.hospital_id,
            hospital_name=m.hospital.name,
            hospital_slug=m.hospital.slug,
            role=m.role.name,
            is_active=m.is_active,
        )
        for m in memberships
    ]

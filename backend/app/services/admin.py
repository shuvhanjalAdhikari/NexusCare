# ================================================================
# NexusCare — app/services/admin.py
# Platform-admin (super-admin) business logic. Operates outside the
# usual tenant-scoping rules in CLAUDE.md §13 — every function here
# is invoked from /api/v1/admin/* routes guarded by require_super_admin.
#
# ROLE SEEDING POLICY
# -------------------
# The roles table has no global seed. Every hospital that is provisioned
# via create_hospital_with_admin gets its own per-hospital copy of the
# seven built-in roles (hospital_admin, doctor, nurse, receptionist,
# pharmacist, lab_technician, billing_staff), all is_custom=False. The
# first admin user receives the hospital_admin role from this set.
#
# TODO: a future bootstrap script — likely backend/scripts/bootstrap_superadmin.py —
# will create the very first platform super-admin (system_role='super_admin',
# no memberships). Until that ships, super-admin rows are inserted by hand
# via pgAdmin/SQL.
# ================================================================

import logging
import uuid
from datetime import datetime
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import UserRole
from app.models.hospital import Hospital, Role
from app.models.membership import HospitalMembership
from app.models.user import User
from app.schemas.admin import HospitalCreateRequest
from app.services.auth import issue_invite_token
from app.utils.exceptions import ConflictError
from app.utils.security import hash_password

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# BUILT-IN ROLES SEEDED INTO EVERY NEW HOSPITAL
# ----------------------------------------------------------------

_BUILTIN_ROLES: list[tuple[str, str]] = [
    (UserRole.HOSPITAL_ADMIN.value, "Hospital owner / administrator. Full access."),
    (UserRole.DOCTOR.value,         "Treating physician. Clinical access."),
    (UserRole.NURSE.value,          "Triage and vitals."),
    (UserRole.RECEPTIONIST.value,   "Appointments and queue management."),
    (UserRole.PHARMACIST.value,     "Drug dispensing."),
    (UserRole.LAB_TECHNICIAN.value, "Lab orders and results."),
    (UserRole.BILLING_STAFF.value,  "Invoices and payments."),
]


# ----------------------------------------------------------------
# CREATE HOSPITAL + FIRST ADMIN
# ----------------------------------------------------------------

async def create_hospital_with_admin(
    db: AsyncSession, payload: HospitalCreateRequest
) -> Tuple[Hospital, User, str, datetime]:
    """
    Atomically provisions a new tenant:
      1. Hospital row (status defaults to 'trial' per schema).
      2. The seven built-in roles, scoped to this hospital.
      3. The first admin User (is_active=False, throwaway password hash).
      4. HospitalMembership linking the admin to this hospital with the
         hospital_admin role.

    Returns (hospital, admin_user, invite_token, invite_expires_at).

    Uses the try/flush/commit/rollback pattern instead of
    `async with db.begin()` because get_db's session already has an
    autobegun transaction (CLAUDE.md §7 Phase-1 flag).
    """
    # Uniqueness pre-checks. The DB also enforces these via UNIQUE
    # constraints; we surface a clean 409 instead of an opaque IntegrityError.
    existing_slug = await db.execute(
        select(Hospital.id).where(Hospital.slug == payload.slug)
    )
    if existing_slug.scalar_one_or_none() is not None:
        raise ConflictError(f"A hospital with slug '{payload.slug}' already exists.")

    existing_email = await db.execute(
        select(User.id).where(User.email == payload.admin_email)
    )
    if existing_email.scalar_one_or_none() is not None:
        # We refuse rather than silently linking the existing user to the new
        # hospital because this is a tenant-creation flow, not an invite flow.
        # The super admin should provision the hospital first, then a regular
        # admin can invite the existing user through the normal /users/invite path.
        raise ConflictError(
            f"A user with email '{payload.admin_email}' already exists. "
            "Provision the hospital with a different admin email, then invite "
            "the existing user via /api/v1/users/invite."
        )

    try:
        hospital = Hospital(
            name=payload.name,
            slug=payload.slug,
            timezone=payload.timezone,
        )
        db.add(hospital)
        await db.flush()

        admin_role_id: uuid.UUID | None = None
        for name, description in _BUILTIN_ROLES:
            role = Role(
                hospital_id=hospital.id,
                name=name,
                description=description,
                is_custom=False,
            )
            db.add(role)
            await db.flush()
            if name == UserRole.HOSPITAL_ADMIN.value:
                admin_role_id = role.id

        assert admin_role_id is not None, "hospital_admin role must be seeded"

        # Throwaway password hash. The account is created is_active=False so
        # it cannot be used to log in until accept_invite rotates the hash
        # and flips the active flag. uuid4().hex gives ~128 bits of entropy.
        admin_user = User(
            first_name=payload.admin_first_name,
            last_name=payload.admin_last_name,
            email=payload.admin_email,
            password_hash=hash_password(uuid.uuid4().hex),
            is_active=False,
        )
        db.add(admin_user)
        await db.flush()

        membership = HospitalMembership(
            user_id=admin_user.id,
            hospital_id=hospital.id,
            role_id=admin_role_id,
            is_active=True,
            invited_by=None,  # platform-level bootstrap, no human inviter
        )
        db.add(membership)
        await db.flush()

        invite_token, expires_at = issue_invite_token(
            admin_user.id, membership.id, admin_user.email
        )

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(hospital)
    await db.refresh(admin_user)

    logger.info(
        "Hospital provisioned",
        extra={
            "hospital_id": str(hospital.id),
            "admin_user_id": str(admin_user.id),
        },
    )
    return hospital, admin_user, invite_token, expires_at

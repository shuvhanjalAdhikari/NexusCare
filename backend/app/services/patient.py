# ================================================================
# NexusCare — app/services/patient.py
# Patient + allergy business logic. All queries are hospital-scoped.
#
# is_active vs deleted_at semantic split:
#   * is_active = False  → suspended/deactivated record. Still visible
#     to admins via list_patients(include_inactive=True). Useful for
#     marking a patient as "do not engage" without losing history.
#   * deleted_at != NULL → soft-deleted record. NEVER returned by any
#     list or get; treated as if it doesn't exist. Used when a
#     registration was a mistake or a duplicate.
#
# patient_allergies has NO foreign-key constraint enforcing that its
# hospital_id equals the parent patient's hospital_id. Every allergy
# operation must therefore first load the parent patient via
# get_patient(...) to confirm tenant ownership before touching any
# allergy row.
#
# Search performance note: ILIKE with leading wildcards cannot use a
# B-tree index — fine to ~100k patients per hospital. A future phase
# can add a pg_trgm GIN index on (first_name, last_name, phone,
# patient_number) or a tsvector column.
# ================================================================

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.patient import Patient, PatientAllergy
from app.schemas.audit import RequestMetadata
from app.schemas.patient import (
    AllergyCreate,
    AllergyUpdate,
    PatientCreate,
    PatientUpdate,
)
from app.services import audit as audit_service
from app.utils.exceptions import NotFoundError, ServerError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# PATIENT NUMBER GENERATION
# ----------------------------------------------------------------

# Crockford-ish base32 alphabet (32 chars, no I/L/O/U/0/1) — unambiguous
# when read aloud or printed on a wristband. 32^6 ~= 1.07B slots per
# hospital; collision probability per insert at 100k rows ~= 1e-4.
_PATIENT_NUMBER_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_PATIENT_NUMBER_RETRIES = 3


def _generate_patient_number() -> str:
    suffix = "".join(secrets.choice(_PATIENT_NUMBER_ALPHABET) for _ in range(6))
    return f"P-{suffix}"


# ----------------------------------------------------------------
# READ
# ----------------------------------------------------------------

async def get_patient(
    db: AsyncSession, hospital_id: uuid.UUID, patient_id: uuid.UUID
) -> Patient:
    """
    Returns the patient with allergies eagerly loaded.
    Cross-tenant access surfaces as NotFoundError (CLAUDE.md §13).
    """
    result = await db.execute(
        select(Patient)
        .options(selectinload(Patient.allergies))
        .where(
            Patient.id == patient_id,
            Patient.hospital_id == hospital_id,
            Patient.deleted_at.is_(None),
        )
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        raise NotFoundError("Patient", patient_id)
    return patient


async def list_patients(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    q: Optional[str] = None,
    gender: Optional[str] = None,
    blood_group: Optional[str] = None,
    include_inactive: bool = False,
    sort: str = "recent",
) -> dict:
    """
    Paginated patient list, scoped to this hospital.

    Filters:
      * q              — ILIKE substring across first_name, last_name,
                         phone, patient_number (case-insensitive).
      * gender         — exact match against the Gender enum value.
      * blood_group    — exact match (free-form string).
      * include_inactive — when False (default), filters out
                         is_active=False patients.

    Soft-deleted patients are NEVER returned regardless of flags.

    Ordering:
      * sort='recent' (default) — created_at DESC. Reception desk
        finds recently-registered patients first; alpha order buries
        the patient who just walked in.
      * sort='name' — first_name ASC, last_name ASC. For audit /
        directory browsing.
    """
    conditions = [
        Patient.hospital_id == hospital_id,
        Patient.deleted_at.is_(None),
    ]
    if not include_inactive:
        conditions.append(Patient.is_active.is_(True))

    if q:
        q_term = f"%{q.strip()}%"
        if q_term != "%%":
            conditions.append(
                or_(
                    Patient.first_name.ilike(q_term),
                    Patient.last_name.ilike(q_term),
                    Patient.phone.ilike(q_term),
                    Patient.patient_number.ilike(q_term),
                )
            )

    if gender:
        conditions.append(Patient.gender == gender)
    if blood_group:
        conditions.append(Patient.blood_group == blood_group)

    stmt = select(Patient).where(and_(*conditions))
    if sort == "name":
        stmt = stmt.order_by(Patient.first_name.asc(), Patient.last_name.asc())
    else:
        stmt = stmt.order_by(Patient.created_at.desc())

    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


async def count_patients(db: AsyncSession, hospital_id: uuid.UUID) -> int:
    """Count of active, non-deleted patients in this hospital. Used by
    future dashboard endpoints."""
    result = await db.execute(
        select(func.count(Patient.id)).where(
            Patient.hospital_id == hospital_id,
            Patient.deleted_at.is_(None),
            Patient.is_active.is_(True),
        )
    )
    return int(result.scalar_one())


# ----------------------------------------------------------------
# CREATE / UPDATE / SOFT DELETE
# ----------------------------------------------------------------

async def create_patient(
    db: AsyncSession, hospital_id: uuid.UUID, payload: PatientCreate
) -> Patient:
    """
    Registers a new patient. Generates a unique patient_number per
    hospital with up to 3 retries on collision (handled via the
    UNIQUE(hospital_id, patient_number) constraint).
    """
    data = payload.model_dump()

    for attempt in range(_PATIENT_NUMBER_RETRIES):
        patient = Patient(
            hospital_id=hospital_id,
            patient_number=_generate_patient_number(),
            **data,
        )
        db.add(patient)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.warning(
                "patient_number collision, retrying",
                extra={"hospital_id": str(hospital_id), "attempt": attempt + 1},
            )
            continue

        logger.info(
            "Patient created",
            extra={
                "hospital_id": str(hospital_id),
                "patient_id": str(patient.id),
            },
        )
        return await get_patient(db, hospital_id, patient.id)

    logger.error(
        "patient_number generation exhausted retries",
        extra={"hospital_id": str(hospital_id)},
    )
    raise ServerError()


async def update_patient(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    patient_id: uuid.UUID,
    payload: PatientUpdate,
) -> Patient:
    """
    Partial update. Only fields explicitly set in the payload are
    written; unset fields are left untouched. patient_number is not
    in PatientUpdate, so it cannot be changed via this endpoint.
    """
    patient = await get_patient(db, hospital_id, patient_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(patient, field, value)

    await db.commit()
    logger.info(
        "Patient updated",
        extra={
            "hospital_id": str(hospital_id),
            "patient_id": str(patient_id),
        },
    )
    return await get_patient(db, hospital_id, patient_id)


async def soft_delete_patient(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    acting_user_id: uuid.UUID,
    acting_membership_id: uuid.UUID,
    request_meta: Optional[RequestMetadata] = None,
) -> None:
    """Soft-delete: stamp deleted_at + flip is_active. Row remains in DB.

    Audit: a 'delete_patient' row is written in the same transaction,
    capturing the patient's key identifying fields before deletion."""
    patient = await get_patient(db, hospital_id, patient_id)
    old_value = {
        "patient_number": patient.patient_number,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "is_active": patient.is_active,
    }
    patient.deleted_at = datetime.now(timezone.utc)
    patient.is_active = False
    await audit_service.log_audit(
        db,
        action="delete_patient",
        resource_type="patient",
        resource_id=patient_id,
        user_id=acting_user_id,
        hospital_id=hospital_id,
        membership_id=acting_membership_id,
        old_value=old_value,
        request_meta=request_meta,
    )
    await db.commit()
    logger.info(
        "Patient soft-deleted",
        extra={
            "hospital_id": str(hospital_id),
            "patient_id": str(patient_id),
        },
    )


# ----------------------------------------------------------------
# ALLERGIES (sub-resource)
# ----------------------------------------------------------------
# Every allergy operation first loads the parent patient via
# get_patient(...) to confirm tenant ownership — the allergies table
# has no FK enforcing hospital_id equality with the parent patient.

async def add_allergy(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    patient_id: uuid.UUID,
    payload: AllergyCreate,
) -> PatientAllergy:
    await get_patient(db, hospital_id, patient_id)

    allergy = PatientAllergy(
        patient_id=patient_id,
        hospital_id=hospital_id,
        **payload.model_dump(),
    )
    db.add(allergy)
    await db.commit()
    await db.refresh(allergy)
    logger.info(
        "Allergy added",
        extra={
            "hospital_id": str(hospital_id),
            "patient_id": str(patient_id),
            "allergy_id": str(allergy.id),
        },
    )
    return allergy


async def list_allergies(
    db: AsyncSession, hospital_id: uuid.UUID, patient_id: uuid.UUID
) -> list[PatientAllergy]:
    """Returns allergies in created_at order (stable display)."""
    patient = await get_patient(db, hospital_id, patient_id)
    return sorted(patient.allergies, key=lambda a: a.created_at)


async def update_allergy(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    patient_id: uuid.UUID,
    allergy_id: uuid.UUID,
    payload: AllergyUpdate,
) -> PatientAllergy:
    await get_patient(db, hospital_id, patient_id)

    result = await db.execute(
        select(PatientAllergy).where(
            PatientAllergy.id == allergy_id,
            PatientAllergy.patient_id == patient_id,
            PatientAllergy.hospital_id == hospital_id,
        )
    )
    allergy = result.scalar_one_or_none()
    if allergy is None:
        raise NotFoundError("Allergy", allergy_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(allergy, field, value)

    await db.commit()
    await db.refresh(allergy)
    logger.info(
        "Allergy updated",
        extra={
            "hospital_id": str(hospital_id),
            "patient_id": str(patient_id),
            "allergy_id": str(allergy_id),
        },
    )
    return allergy


async def delete_allergy(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    patient_id: uuid.UUID,
    allergy_id: uuid.UUID,
) -> None:
    """Hard delete — allergies have no deleted_at column per 01_schema.sql."""
    await get_patient(db, hospital_id, patient_id)

    result = await db.execute(
        select(PatientAllergy).where(
            PatientAllergy.id == allergy_id,
            PatientAllergy.patient_id == patient_id,
            PatientAllergy.hospital_id == hospital_id,
        )
    )
    allergy = result.scalar_one_or_none()
    if allergy is None:
        raise NotFoundError("Allergy", allergy_id)

    await db.delete(allergy)
    await db.commit()
    logger.info(
        "Allergy deleted",
        extra={
            "hospital_id": str(hospital_id),
            "patient_id": str(patient_id),
            "allergy_id": str(allergy_id),
        },
    )

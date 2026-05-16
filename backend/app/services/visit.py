# ================================================================
# NexusCare — app/services/visit.py
# Clinical visit business logic + its vitals and diagnoses
# sub-resources. All queries are hospital-scoped (CLAUDE.md §13).
#
# Authorization: v1 grants visit access to all hospital members.
# Role-based restrictions (e.g. clinical-only for vitals) are a v2
# enhancement.
#
# Visit state machine (PATCH /visits transitions only):
#   waiting   → active | cancelled
#   active    → completed | cancelled
#   completed → closed
#   closed / cancelled → terminal
# completed_at is stamped the moment a visit enters 'completed'.
#
# Visit creation is EXPLICIT: a doctor POSTs /visits when a
# consultation begins. The OPD queue transition to 'in_consultation'
# does NOT auto-create a visit — it only moves the queue entry.
#
# Soft delete: a deleted visit (deleted_at != NULL) is never returned.
# Its vitals/diagnoses are only reachable through the visit, so they
# need no separate filter — once the visit 404s they are unreachable.
# Vitals and diagnoses themselves are hard-deleted (no deleted_at).
#
# BMI: computed server-side whenever both weight_kg and height_cm are
# present, overwriting any client-supplied bmi. With only one of the
# two, the client value (or NULL) is kept.
#
# Tenant note: visits.patient_id / doctor_id carry no FK or CHECK
# enforcing hospital equality, so create_visit loads both parents
# hospital-scoped before inserting.
# ================================================================

import logging
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.enums import VisitStatus
from app.models.appointment import Appointment, OPDQueue
from app.models.doctor import DoctorProfile
from app.models.patient import Patient
from app.models.visit import Visit, VisitDiagnosis, Vital
from app.schemas.visit import (
    DiagnosisCreate,
    DiagnosisUpdate,
    VisitCreate,
    VisitUpdate,
    VitalCreate,
    VitalUpdate,
)
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.pagination import make_paged_response, paginate

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------------

_VISIT_TRANSITIONS: dict[str, set[str]] = {
    VisitStatus.WAITING.value: {
        VisitStatus.ACTIVE.value,
        VisitStatus.CANCELLED.value,
    },
    VisitStatus.ACTIVE.value: {
        VisitStatus.COMPLETED.value,
        VisitStatus.CANCELLED.value,
    },
    VisitStatus.COMPLETED.value: {
        VisitStatus.CLOSED.value,
    },
    VisitStatus.CLOSED.value: set(),
    VisitStatus.CANCELLED.value: set(),
}


# ----------------------------------------------------------------
# BMI
# ----------------------------------------------------------------

def _compute_bmi(
    weight_kg: Optional[Decimal], height_cm: Optional[Decimal]
) -> Optional[Decimal]:
    """BMI = weight(kg) / height(m)^2, rounded to 1 decimal place.
    Returns None unless both inputs are present and height > 0."""
    if weight_kg is None or height_cm is None:
        return None
    height_m = Decimal(height_cm) / Decimal(100)
    if height_m <= 0:
        return None
    bmi = Decimal(weight_kg) / (height_m * height_m)
    return bmi.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------
# INTERNAL LOADERS / VERIFIERS
# ----------------------------------------------------------------

async def _load_visit(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    *,
    with_detail: bool = False,
) -> Visit:
    """Load a non-deleted visit within the tenant. Cross-tenant or
    missing rows surface as NotFoundError (CLAUDE.md §13).

    with_detail eager-loads vitals, diagnoses and referrals."""
    stmt = select(Visit).where(
        Visit.id == visit_id,
        Visit.hospital_id == hospital_id,
        Visit.deleted_at.is_(None),
    )
    if with_detail:
        stmt = stmt.options(
            selectinload(Visit.vitals),
            selectinload(Visit.diagnoses),
            selectinload(Visit.referrals),
        )
    result = await db.execute(stmt)
    visit = result.scalar_one_or_none()
    if visit is None:
        raise NotFoundError("Visit", visit_id)
    return visit


async def _verify_patient(
    db: AsyncSession, hospital_id: uuid.UUID, patient_id: uuid.UUID
) -> None:
    """Confirm a patient belongs to this hospital and is not soft-deleted."""
    result = await db.execute(
        select(Patient.id).where(
            Patient.id == patient_id,
            Patient.hospital_id == hospital_id,
            Patient.deleted_at.is_(None),
        )
    )
    if result.first() is None:
        raise NotFoundError("Patient", patient_id)


async def _verify_doctor(
    db: AsyncSession, hospital_id: uuid.UUID, doctor_id: uuid.UUID
) -> None:
    """Confirm a doctor profile belongs to this hospital."""
    result = await db.execute(
        select(DoctorProfile.id).where(
            DoctorProfile.id == doctor_id,
            DoctorProfile.hospital_id == hospital_id,
        )
    )
    if result.first() is None:
        raise NotFoundError("Doctor", doctor_id)


# ----------------------------------------------------------------
# VISIT — READ
# ----------------------------------------------------------------

async def get_visit(
    db: AsyncSession, hospital_id: uuid.UUID, visit_id: uuid.UUID
) -> Visit:
    """Return one visit with vitals, diagnoses and referrals loaded."""
    return await _load_visit(db, hospital_id, visit_id, with_detail=True)


async def list_visits(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    page: int,
    size: int,
    *,
    patient_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> dict:
    """
    Paginated visit list scoped to this hospital, ordered by created_at
    DESC (most recent encounter first). from_date / to_date bound
    created_at inclusively.
    """
    conditions = [
        Visit.hospital_id == hospital_id,
        Visit.deleted_at.is_(None),
    ]
    if patient_id is not None:
        conditions.append(Visit.patient_id == patient_id)
    if doctor_id is not None:
        conditions.append(Visit.doctor_id == doctor_id)
    if status is not None:
        conditions.append(Visit.status == status)
    if from_date is not None:
        conditions.append(Visit.created_at >= from_date)
    if to_date is not None:
        conditions.append(Visit.created_at <= to_date)

    stmt = select(Visit).where(*conditions).order_by(Visit.created_at.desc())
    items, total = await paginate(db, stmt, page, size)
    return make_paged_response(items=items, total=total, page=page, size=size)


# ----------------------------------------------------------------
# VISIT — CREATE
# ----------------------------------------------------------------

async def create_visit(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    payload: VisitCreate,
    *,
    created_by: uuid.UUID,
    created_by_membership_id: uuid.UUID,
) -> Visit:
    """
    Start a new clinical visit. The visit opens in status 'waiting'.

    When appointment_id / queue_id are supplied they must reference the
    same patient + doctor as the visit, or a BadRequestError is raised.
    """
    await _verify_patient(db, hospital_id, payload.patient_id)
    await _verify_doctor(db, hospital_id, payload.doctor_id)

    if payload.appointment_id is not None:
        result = await db.execute(
            select(Appointment).where(
                Appointment.id == payload.appointment_id,
                Appointment.hospital_id == hospital_id,
                Appointment.deleted_at.is_(None),
            )
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            raise NotFoundError("Appointment", payload.appointment_id)
        if (
            appointment.patient_id != payload.patient_id
            or appointment.doctor_id != payload.doctor_id
        ):
            raise BadRequestError(
                "appointment_id references a different patient or doctor."
            )

    if payload.queue_id is not None:
        result = await db.execute(
            select(OPDQueue).where(
                OPDQueue.id == payload.queue_id,
                OPDQueue.hospital_id == hospital_id,
            )
        )
        queue_entry = result.scalar_one_or_none()
        if queue_entry is None:
            raise NotFoundError("Queue entry", payload.queue_id)
        if (
            queue_entry.patient_id != payload.patient_id
            or queue_entry.doctor_id != payload.doctor_id
        ):
            raise BadRequestError(
                "queue_id references a different patient or doctor."
            )

    visit = Visit(
        hospital_id=hospital_id,
        status=VisitStatus.WAITING.value,
        created_by=created_by,
        created_by_membership_id=created_by_membership_id,
        **payload.model_dump(),
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    logger.info(
        "Visit created",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit.id),
            "doctor_id": str(payload.doctor_id),
        },
    )
    return visit


# ----------------------------------------------------------------
# VISIT — UPDATE
# ----------------------------------------------------------------

async def update_visit(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: VisitUpdate,
    *,
    updated_by: uuid.UUID,
    updated_by_membership_id: uuid.UUID,
) -> Visit:
    """
    Partial update of the SOAP notes and/or status. A status change is
    validated against the visit state machine; entering 'completed'
    stamps completed_at.
    """
    visit = await _load_visit(db, hospital_id, visit_id)

    data = payload.model_dump(exclude_unset=True)
    new_status: Optional[VisitStatus] = data.pop("status", None)

    if new_status is not None and new_status.value != visit.status:
        target = new_status.value
        allowed = _VISIT_TRANSITIONS.get(visit.status, set())
        if target not in allowed:
            logger.warning(
                "Rejected visit status transition",
                extra={
                    "hospital_id": str(hospital_id),
                    "visit_id": str(visit_id),
                },
            )
            raise BadRequestError(
                f"Cannot change visit status from '{visit.status}' to '{target}'."
            )
        visit.status = target
        if target == VisitStatus.COMPLETED.value:
            visit.completed_at = datetime.now(timezone.utc)

    for field, value in data.items():
        setattr(visit, field, value)

    visit.updated_by = updated_by
    visit.updated_by_membership_id = updated_by_membership_id

    await db.commit()
    await db.refresh(visit)
    logger.info(
        "Visit updated",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "status": visit.status,
        },
    )
    return visit


async def soft_delete_visit(
    db: AsyncSession, hospital_id: uuid.UUID, visit_id: uuid.UUID
) -> None:
    """Soft-delete a visit — stamp deleted_at. Status is left unchanged;
    the row remains in the DB. Nested vitals/diagnoses become
    unreachable along with it."""
    visit = await _load_visit(db, hospital_id, visit_id)
    visit.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "Visit soft-deleted",
        extra={"hospital_id": str(hospital_id), "visit_id": str(visit_id)},
    )


# ----------------------------------------------------------------
# VITALS (sub-resource)
# ----------------------------------------------------------------
# Each vitals operation first loads the parent visit hospital-scoped so
# cross-tenant access surfaces as NotFoundError on the visit.

async def add_vital(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: VitalCreate,
    *,
    recorded_by: uuid.UUID,
    recorded_by_membership_id: uuid.UUID,
) -> Vital:
    """Record a vitals snapshot. BMI is computed server-side when both
    weight_kg and height_cm are supplied."""
    await _load_visit(db, hospital_id, visit_id)

    data = payload.model_dump()
    if data.get("weight_kg") is not None and data.get("height_cm") is not None:
        data["bmi"] = _compute_bmi(data["weight_kg"], data["height_cm"])

    vital = Vital(
        visit_id=visit_id,
        hospital_id=hospital_id,
        recorded_by=recorded_by,
        recorded_by_membership_id=recorded_by_membership_id,
        **data,
    )
    db.add(vital)
    await db.commit()
    await db.refresh(vital)
    logger.info(
        "Vital recorded",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "vital_id": str(vital.id),
        },
    )
    return vital


async def list_vitals(
    db: AsyncSession, hospital_id: uuid.UUID, visit_id: uuid.UUID
) -> list[Vital]:
    """Return this visit's vitals in recorded_at order."""
    await _load_visit(db, hospital_id, visit_id)
    result = await db.execute(
        select(Vital)
        .where(Vital.visit_id == visit_id, Vital.hospital_id == hospital_id)
        .order_by(Vital.recorded_at.asc())
    )
    return list(result.scalars().all())


async def _load_vital(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    vital_id: uuid.UUID,
) -> Vital:
    result = await db.execute(
        select(Vital).where(
            Vital.id == vital_id,
            Vital.visit_id == visit_id,
            Vital.hospital_id == hospital_id,
        )
    )
    vital = result.scalar_one_or_none()
    if vital is None:
        raise NotFoundError("Vital", vital_id)
    return vital


async def update_vital(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    vital_id: uuid.UUID,
    payload: VitalUpdate,
) -> Vital:
    """Correct a vitals reading. recorded_by is intentionally left with
    the original recorder. BMI is recomputed from the merged weight_kg
    + height_cm when both are present after the patch."""
    await _load_visit(db, hospital_id, visit_id)
    vital = await _load_vital(db, hospital_id, visit_id, vital_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(vital, field, value)

    if vital.weight_kg is not None and vital.height_cm is not None:
        vital.bmi = _compute_bmi(vital.weight_kg, vital.height_cm)

    await db.commit()
    await db.refresh(vital)
    logger.info(
        "Vital updated",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "vital_id": str(vital_id),
        },
    )
    return vital


async def delete_vital(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    vital_id: uuid.UUID,
) -> None:
    """Hard-delete a vitals reading — vitals have no deleted_at column."""
    await _load_visit(db, hospital_id, visit_id)
    vital = await _load_vital(db, hospital_id, visit_id, vital_id)
    await db.delete(vital)
    await db.commit()
    logger.info(
        "Vital deleted",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "vital_id": str(vital_id),
        },
    )


# ----------------------------------------------------------------
# DIAGNOSES (sub-resource)
# ----------------------------------------------------------------

async def add_diagnosis(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    payload: DiagnosisCreate,
) -> VisitDiagnosis:
    """Record a diagnosis on a visit."""
    await _load_visit(db, hospital_id, visit_id)

    diagnosis = VisitDiagnosis(
        visit_id=visit_id,
        hospital_id=hospital_id,
        icd_code=payload.icd_code,
        diagnosis_text=payload.diagnosis_text,
        diagnosis_type=payload.diagnosis_type.value,
        is_chronic=payload.is_chronic,
    )
    db.add(diagnosis)
    await db.commit()
    await db.refresh(diagnosis)
    logger.info(
        "Diagnosis recorded",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "diagnosis_id": str(diagnosis.id),
        },
    )
    return diagnosis


async def list_diagnoses(
    db: AsyncSession, hospital_id: uuid.UUID, visit_id: uuid.UUID
) -> list[VisitDiagnosis]:
    """Return this visit's diagnoses in created_at order."""
    await _load_visit(db, hospital_id, visit_id)
    result = await db.execute(
        select(VisitDiagnosis)
        .where(
            VisitDiagnosis.visit_id == visit_id,
            VisitDiagnosis.hospital_id == hospital_id,
        )
        .order_by(VisitDiagnosis.created_at.asc())
    )
    return list(result.scalars().all())


async def _load_diagnosis(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
) -> VisitDiagnosis:
    result = await db.execute(
        select(VisitDiagnosis).where(
            VisitDiagnosis.id == diagnosis_id,
            VisitDiagnosis.visit_id == visit_id,
            VisitDiagnosis.hospital_id == hospital_id,
        )
    )
    diagnosis = result.scalar_one_or_none()
    if diagnosis is None:
        raise NotFoundError("Diagnosis", diagnosis_id)
    return diagnosis


async def update_diagnosis(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
    payload: DiagnosisUpdate,
) -> VisitDiagnosis:
    """Partial update of a diagnosis."""
    await _load_visit(db, hospital_id, visit_id)
    diagnosis = await _load_diagnosis(db, hospital_id, visit_id, diagnosis_id)

    data = payload.model_dump(exclude_unset=True)
    if "diagnosis_type" in data and data["diagnosis_type"] is not None:
        data["diagnosis_type"] = data["diagnosis_type"].value
    for field, value in data.items():
        setattr(diagnosis, field, value)

    await db.commit()
    await db.refresh(diagnosis)
    logger.info(
        "Diagnosis updated",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "diagnosis_id": str(diagnosis_id),
        },
    )
    return diagnosis


async def delete_diagnosis(
    db: AsyncSession,
    hospital_id: uuid.UUID,
    visit_id: uuid.UUID,
    diagnosis_id: uuid.UUID,
) -> None:
    """Hard-delete a diagnosis — visit_diagnoses has no deleted_at column."""
    await _load_visit(db, hospital_id, visit_id)
    diagnosis = await _load_diagnosis(db, hospital_id, visit_id, diagnosis_id)
    await db.delete(diagnosis)
    await db.commit()
    logger.info(
        "Diagnosis deleted",
        extra={
            "hospital_id": str(hospital_id),
            "visit_id": str(visit_id),
            "diagnosis_id": str(diagnosis_id),
        },
    )

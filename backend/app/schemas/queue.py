# ================================================================
# NexusCare — app/schemas/queue.py
# Pydantic v2 schemas for the OPD queue module:
#   * Adding to the queue — check-in OR walk-in (one request shape)
#   * Queue status updates
#   * Today's per-doctor stats
#
# hospital_id is NEVER accepted from the body — it comes from the JWT.
# queue_number is server-assigned (atomic per doctor per day) and is
# never accepted or updated from the client.
# ================================================================

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants.enums import QueuePriority, QueueStatus


# ----------------------------------------------------------------
# NESTED DETAIL
# ----------------------------------------------------------------

class QueuePatientInfo(BaseModel):
    """Lean patient identity embedded in a queue entry response — the
    live OPD board needs the name, not just an id."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_number: str
    first_name: str
    last_name: str
    phone: Optional[str] = None


# ----------------------------------------------------------------
# QUEUE ADD — check-in OR walk-in
# ----------------------------------------------------------------

class QueueAddRequest(BaseModel):
    """Body for POST /api/v1/queue. Handles two mutually exclusive cases:

      * Check-in  — supply appointment_id ONLY. patient_id, doctor_id
        and priority are derived from the appointment.
      * Walk-in   — supply patient_id AND doctor_id (no appointment_id).
        priority is optional and defaults to 'normal'.

    counter_no is optional in both cases.
    """

    appointment_id: Optional[UUID] = None
    patient_id: Optional[UUID] = None
    doctor_id: Optional[UUID] = None
    priority: QueuePriority = QueuePriority.NORMAL
    counter_no: Optional[str] = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _exactly_one_mode(self) -> "QueueAddRequest":
        is_checkin = self.appointment_id is not None
        is_walkin = self.patient_id is not None or self.doctor_id is not None
        if is_checkin and is_walkin:
            raise ValueError(
                "Provide either appointment_id (check-in) or "
                "patient_id+doctor_id (walk-in), not both."
            )
        if not is_checkin and not is_walkin:
            raise ValueError(
                "Provide appointment_id to check in an appointment, or "
                "patient_id+doctor_id to add a walk-in."
            )
        if is_walkin and (self.patient_id is None or self.doctor_id is None):
            raise ValueError("A walk-in requires both patient_id and doctor_id.")
        return self


class QueueUpdate(BaseModel):
    """Body for PATCH /api/v1/queue/{id}. All fields optional.
    status transitions are validated against the queue state machine."""

    status: Optional[QueueStatus] = None
    counter_no: Optional[str] = Field(default=None, max_length=10)
    estimated_wait_minutes: Optional[int] = Field(default=None, ge=0)


# ----------------------------------------------------------------
# QUEUE RESPONSE
# ----------------------------------------------------------------

class QueueResponse(BaseModel):
    """A queue entry with embedded patient identity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    appointment_id: Optional[UUID] = None
    patient_id: UUID
    doctor_id: UUID
    queue_number: int
    priority: QueuePriority
    status: QueueStatus
    counter_no: Optional[str] = None
    estimated_wait_minutes: Optional[int] = None
    checked_in_at: Optional[datetime] = None
    called_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    patient: QueuePatientInfo


# ----------------------------------------------------------------
# TODAY STATS
# ----------------------------------------------------------------

class TodayStatsResponse(BaseModel):
    """Per-doctor counts for the current day (hospital timezone).

    Mixed source — every count derives from opd_queue EXCEPT no_show,
    which derives from appointments (the queue has no no_show status).
    This mirrors operational reality: the queue tracks live flow, while
    no_show is reconciled at end-of-day from unattended appointments."""

    doctor_id: UUID
    date: date
    total_in_queue: int
    waiting: int
    called: int
    in_consultation: int
    completed: int
    skipped: int
    walk_ins: int
    no_show: int

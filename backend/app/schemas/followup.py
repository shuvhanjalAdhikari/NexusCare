# ================================================================
# NexusCare — app/schemas/followup.py
# Pydantic v2 schemas for scheduled follow-ups.
#
# Schema reality (01_schema.sql): the date column is 'recommended_date'
# and the free-text column is 'notes' (the Phase 12 brief called them
# follow_up_date / reason — the schema wins). Status values are
# pending / completed / missed / cancelled.
#
# patient_id and visit_id are NEVER accepted from the body — they are
# taken from the visit the follow-up is created under.
# ================================================================

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.constants.enums import FollowupStatus
from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# CREATE / UPDATE
# ----------------------------------------------------------------

class FollowupCreate(BaseModel):
    """
    Body for POST /api/v1/visits/{visit_id}/followups.

    doctor_id is optional — when omitted it defaults to the doctor on
    the visit the follow-up is created under.
    """

    recommended_date: date
    notes: Optional[str] = None
    doctor_id: Optional[UUID] = None


class FollowupUpdate(BaseModel):
    """
    Body for PATCH /api/v1/followups/{id}. All fields optional.

    A status change is validated against the follow-up state machine
    (pending → completed | cancelled | missed; all three terminal).
    """

    recommended_date: Optional[date] = None
    notes: Optional[str] = None
    status: Optional[FollowupStatus] = None


# ----------------------------------------------------------------
# RESPONSE
# ----------------------------------------------------------------

class FollowupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    patient_id: UUID
    visit_id: UUID
    doctor_id: UUID
    recommended_date: date
    status: FollowupStatus
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


FollowupListResponse = PagedResponse[FollowupResponse]

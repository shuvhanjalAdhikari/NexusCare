# ================================================================
# NexusCare — app/schemas/feedback.py
# Pydantic v2 schemas for patient satisfaction feedback.
#
# Schema reality (01_schema.sql): feedback.patient_id is NOT NULL, so
# patient_id is REQUIRED on submission. The table links to
# appointment_id (there is no visit_id column) and has four separate
# 1-5 rating columns plus a free-text 'comment'. There is no
# 'submitted_via' column — that field from the brief was dropped.
#
# Feedback is immutable: there is no FeedbackUpdate schema. Corrections
# happen via delete + re-create.
# ================================================================

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.pagination import PagedResponse


# ----------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------

class FeedbackCreate(BaseModel):
    """
    Body for POST /api/v1/feedback.

    patient_id is required (DB NOT NULL). appointment_id and doctor_id
    are optional links. All four ratings are optional and bounded 1-5.

    Anonymity: set is_anonymous=true. The patient is still linked via
    patient_id internally — the flag only controls whether the patient
    identity is shown in admin views. Truly unlinked anonymous feedback
    is deferred to the v2 patient portal.
    """

    patient_id: UUID
    appointment_id: Optional[UUID] = None
    doctor_id: Optional[UUID] = None
    rating_overall: Optional[int] = Field(default=None, ge=1, le=5)
    rating_doctor: Optional[int] = Field(default=None, ge=1, le=5)
    rating_wait_time: Optional[int] = Field(default=None, ge=1, le=5)
    rating_cleanliness: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = None
    is_anonymous: bool = False


# ----------------------------------------------------------------
# RESPONSE
# ----------------------------------------------------------------

class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    patient_id: UUID
    appointment_id: Optional[UUID]
    doctor_id: Optional[UUID]
    rating_overall: Optional[int]
    rating_doctor: Optional[int]
    rating_wait_time: Optional[int]
    rating_cleanliness: Optional[int]
    comment: Optional[str]
    is_anonymous: bool
    submitted_at: datetime


FeedbackListResponse = PagedResponse[FeedbackResponse]

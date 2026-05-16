# ================================================================
# NexusCare — app/schemas/referral.py
# Pydantic v2 schemas for the referral module.
#
# hospital_id, visit_id and from_doctor_id are NEVER accepted from the
# request body:
#   * hospital_id   comes from the JWT.
#   * visit_id      comes from the /visits/{visit_id}/referrals path.
#   * from_doctor_id is derived from the parent visit's doctor_id.
#
# referral_type mutual-exclusivity is enforced here at the schema
# layer (model_validator) so a malformed referral is rejected with a
# 422 before it ever reaches the service:
#   * internal → to_doctor_id required, external_hospital forbidden
#   * external → external_hospital required, to_doctor_id forbidden
# The service additionally verifies an internal to_doctor_id belongs
# to the current hospital (NotFoundError — never leak other tenants).
#
# Inter-tenant referrals (across NexusCare hospitals) are deferred to
# v2; 'external' here means a free-text outside facility, not another
# tenant.
# ================================================================

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.constants.enums import ReferralStatus, ReferralType, ReferralUrgency


# ----------------------------------------------------------------
# REFERRAL SCHEMAS
# ----------------------------------------------------------------

class ReferralCreate(BaseModel):
    """Body for POST /api/v1/visits/{visit_id}/referrals."""

    referral_type: ReferralType
    to_doctor_id: Optional[UUID] = None
    to_department_id: Optional[UUID] = None
    external_hospital: Optional[str] = None
    reason: str
    urgency: ReferralUrgency = ReferralUrgency.ROUTINE
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_mutual_exclusivity(self) -> "ReferralCreate":
        if self.referral_type == ReferralType.INTERNAL:
            if self.to_doctor_id is None:
                raise ValueError("An internal referral requires to_doctor_id.")
            if self.external_hospital is not None:
                raise ValueError(
                    "An internal referral must not set external_hospital."
                )
        elif self.referral_type == ReferralType.EXTERNAL:
            if not self.external_hospital:
                raise ValueError(
                    "An external referral requires external_hospital."
                )
            if self.to_doctor_id is not None:
                raise ValueError(
                    "An external referral must not set to_doctor_id."
                )
        return self


class ReferralUpdate(BaseModel):
    """Body for PATCH /api/v1/referrals/{id}. All fields optional.

    status transitions are validated against the referral state
    machine in the service layer."""

    status: Optional[ReferralStatus] = None
    urgency: Optional[ReferralUrgency] = None
    notes: Optional[str] = None


class ReferralResponse(BaseModel):
    """Flat referral shape — serialized directly from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hospital_id: UUID
    visit_id: UUID
    from_doctor_id: UUID
    to_doctor_id: Optional[UUID] = None
    to_department_id: Optional[UUID] = None
    referral_type: ReferralType
    external_hospital: Optional[str] = None
    reason: str
    urgency: ReferralUrgency
    status: ReferralStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------
# PAGINATED LIST
# ----------------------------------------------------------------

# PagedResponse import kept local to avoid a circular import at module
# load — pagination imports nothing from schemas.
from app.utils.pagination import PagedResponse  # noqa: E402

ReferralListResponse = PagedResponse[ReferralResponse]

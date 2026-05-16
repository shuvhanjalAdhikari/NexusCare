# ================================================================
# NexusCare — app/dependencies/hospital.py
# Tenant-scoping dependency. Chained off get_current_membership so the
# membership has already been re-validated by the time we get here.
# ================================================================

import uuid
from typing import Annotated

from fastapi import Depends

from app.constants.enums import HospitalStatus
from app.dependencies.auth import get_current_membership
from app.models.membership import HospitalMembership
from app.utils.exceptions import HospitalSuspendedError


async def get_hospital_id(
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
) -> uuid.UUID:
    """
    Return the active hospital_id for this request, after confirming
    the hospital is not suspended. Performed on every request because
    JWTs outlive permission and tenant-status changes.
    """
    if membership.hospital.status == HospitalStatus.SUSPENDED.value:
        raise HospitalSuspendedError()
    return membership.hospital_id


async def get_hospital_timezone(
    membership: Annotated[HospitalMembership, Depends(get_current_membership)],
) -> str:
    """
    Return this hospital's IANA timezone string (e.g. 'Asia/Kathmandu').

    Used by the appointment/queue modules to anchor "today" and slot
    generation to the hospital's local day rather than UTC. The column
    is NOT NULL DEFAULT 'UTC' in the schema, so this never returns None;
    an unrecognised value is tolerated and falls back to UTC downstream.
    """
    return membership.hospital.timezone

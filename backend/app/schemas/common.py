# ================================================================
# NexusCare — schemas/common.py
# Shared Pydantic schemas used across multiple modules.
# ================================================================

from typing import Any, Optional

from pydantic import BaseModel

from app.utils.pagination import PagedResponse  # noqa: F401 — re-export for router convenience


# ----------------------------------------------------------------
# SUCCESS RESPONSES
# ----------------------------------------------------------------

class MessageResponse(BaseModel):
    """Returned by endpoints that produce no resource body (e.g., soft-delete)."""

    message: str


# ----------------------------------------------------------------
# ERROR RESPONSE
# ----------------------------------------------------------------

class ErrorResponse(BaseModel):
    """
    Mirrors the detail shape emitted by NexusCareException.
    Use as response_model on error status codes in OpenAPI docs.
    """

    error: str
    message: str
    status_code: int
    details: Optional[Any] = None

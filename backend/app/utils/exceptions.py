# ================================================================
# NexusCare — utils/exceptions.py
# Custom HTTP exceptions with consistent error response shapes.
# Never raise raw HTTPException outside this file.
# ================================================================

from typing import Any, Optional
from fastapi import HTTPException, status


# ----------------------------------------------------------------
# BASE EXCEPTION
# ----------------------------------------------------------------

class NexusCareException(HTTPException):
    """
    Base exception for all NexusCare custom exceptions.
    Ensures every error response has a consistent shape:
    {
        "error": "ERROR_CODE",
        "message": "Human readable message",
        "status_code": 404
    }
    """

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        details: Optional[Any] = None,
    ) -> None:
        self.error = error
        self.message = message
        self.details = details
        super().__init__(
            status_code=status_code,
            detail={
                "error": error,
                "message": message,
                "status_code": status_code,
                **({"details": details} if details else {}),
            },
        )


# ----------------------------------------------------------------
# 400 BAD REQUEST
# ----------------------------------------------------------------

class BadRequestError(NexusCareException):
    """
    Raised when the request is malformed or contains
    invalid data that passes Pydantic validation but
    fails business logic validation.

    Example: booking an appointment on a doctor's day off.
    """

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="BAD_REQUEST",
            message=message,
            details=details,
        )


# ----------------------------------------------------------------
# 401 UNAUTHORIZED
# ----------------------------------------------------------------

class UnauthorizedError(NexusCareException):
    """
    Raised when a request is made without valid
    authentication credentials or with an expired token.

    Example: missing or expired JWT token.
    """

    def __init__(
        self,
        message: str = "Authentication required. Please log in.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="UNAUTHORIZED",
            message=message,
        )


# ----------------------------------------------------------------
# 403 FORBIDDEN
# ----------------------------------------------------------------

class ForbiddenError(NexusCareException):
    """
    Raised when an authenticated user attempts an action
    their role does not permit.

    Example: a receptionist trying to write clinical notes.
    """

    def __init__(
        self,
        message: str = "You do not have permission to perform this action.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error="FORBIDDEN",
            message=message,
        )


# ----------------------------------------------------------------
# 404 NOT FOUND
# ----------------------------------------------------------------

class NotFoundError(NexusCareException):
    """
    Raised when a requested resource does not exist
    or belongs to a different hospital (tenant isolation).

    Example: patient id not found in current hospital.
    """

    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error=f"{resource.upper()}_NOT_FOUND",
            message=f"{resource} with identifier '{identifier}' was not found.",
        )


# ----------------------------------------------------------------
# 409 CONFLICT
# ----------------------------------------------------------------

class ConflictError(NexusCareException):
    """
    Raised when a resource already exists or an action
    conflicts with current system state.

    Example: registering a patient with a phone number
    that already exists in this hospital.
    """

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error="CONFLICT",
            message=message,
            details=details,
        )


# ----------------------------------------------------------------
# 422 UNPROCESSABLE ENTITY
# ----------------------------------------------------------------

class ValidationError(NexusCareException):
    """
    Raised when data passes Pydantic schema validation
    but fails deeper business rule validation.

    Example: prescription quantity exceeds available stock.
    """

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error="VALIDATION_ERROR",
            message=message,
            details=details,
        )


# ----------------------------------------------------------------
# 429 TOO MANY REQUESTS
# ----------------------------------------------------------------

class RateLimitError(NexusCareException):
    """
    Raised when a user exceeds the allowed request rate.

    Example: too many failed login attempts.
    """

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error="RATE_LIMIT_EXCEEDED",
            message=message,
        )


# ----------------------------------------------------------------
# 500 INTERNAL SERVER ERROR
# ----------------------------------------------------------------

class ServerError(NexusCareException):
    """
    Raised when an unexpected server-side error occurs.
    Never expose internal error details to the client.

    Example: database connection failure.
    """

    def __init__(
        self,
        message: str = "An unexpected error occurred. Please try again.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="INTERNAL_SERVER_ERROR",
            message=message,
        )


# ----------------------------------------------------------------
# DOMAIN SPECIFIC EXCEPTIONS
# These extend the base exceptions above with specific
# error codes for common NexusCare business scenarios.
# ----------------------------------------------------------------

class InvalidCredentialsError(UnauthorizedError):
    """Raised when email or password is incorrect during login."""

    def __init__(self) -> None:
        super().__init__(
            message="Invalid email or password. Please try again."
        )


class TokenExpiredError(UnauthorizedError):
    """Raised when a JWT token has expired."""

    def __init__(self) -> None:
        super().__init__(
            message="Your session has expired. Please log in again."
        )


class SelectionTokenRequiredError(UnauthorizedError):
    """
    Raised when the JWT 'type' claim does not match what the route expects.

    A selection token presented to a protected route, or an access token
    presented to /select-workspace, both surface as this error so attackers
    cannot distinguish the two cases.
    """

    def __init__(self) -> None:
        super().__init__(
            message="Invalid token for this operation. Please log in again."
        )


class InactiveUserError(ForbiddenError):
    """Raised when a deactivated user attempts to log in."""

    def __init__(self) -> None:
        super().__init__(
            message="Your account has been deactivated. Contact your administrator."
        )


class HospitalSuspendedError(ForbiddenError):
    """Raised when a user from a suspended hospital tries to access the system."""

    def __init__(self) -> None:
        super().__init__(
            message="Your hospital account has been suspended. Contact NexusCare support."
        )


class DuplicatePatientError(ConflictError):
    """Raised when registering a patient that already exists in this hospital."""

    def __init__(self, phone: str) -> None:
        super().__init__(
            message=f"A patient with phone number '{phone}' already exists in this hospital."
        )


class SlotUnavailableError(ConflictError):
    """Raised when trying to book an already taken appointment slot."""

    def __init__(self) -> None:
        super().__init__(
            message="This appointment slot is no longer available. Please choose another time."
        )


class DoctorOnLeaveError(ConflictError):
    """Raised when booking an appointment on a doctor's approved leave date."""

    def __init__(self) -> None:
        super().__init__(
            message="The selected doctor is on leave on this date. Please choose another date or doctor."
        )


class InsufficientStockError(ValidationError):
    """Raised when dispensing more drug quantity than available in batch."""

    def __init__(self, drug_name: str, available: int) -> None:
        super().__init__(
            message=f"Insufficient stock for '{drug_name}'. Only {available} units available."
        )


class InvoiceAlreadyPaidError(ConflictError):
    """Raised when attempting to modify or void an already paid invoice."""

    def __init__(self) -> None:
        super().__init__(
            message="This invoice has already been paid and cannot be modified."
        )
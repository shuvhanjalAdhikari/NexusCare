# ================================================================
# NexusCare — app/models/__init__.py
# Import all models so SQLAlchemy registers them with Base.metadata
# before any call to create_all() or mapper configuration.
# ================================================================

from app.models.hospital import Hospital, Role, Permission, RolePermission
from app.models.user import User
from app.models.membership import HospitalMembership
from app.models.patient import Patient, PatientAllergy
from app.models.doctor import (
    Department,
    DoctorProfile,
    DoctorSchedule,
    DoctorLeave,
    DoctorScheduleOverride,
)
from app.models.appointment import Appointment, OPDQueue
from app.models.visit import Visit, Vital, VisitDiagnosis, Referral
from app.models.prescription import (
    Drug,
    DrugBatch,
    Prescription,
    PrescriptionItem,
    DispenseLog,
)
from app.models.lab import LabTest, LabOrder, LabResult
from app.models.billing import Service, Invoice, InvoiceItem, Payment
from app.models.attachment import Attachment
from app.models.notification import Notification
from app.models.followup import Followup, Feedback
from app.models.audit import AuditLog

__all__ = [
    "Hospital", "Role", "Permission", "RolePermission",
    "User",
    "HospitalMembership",
    "Patient", "PatientAllergy",
    "Department", "DoctorProfile", "DoctorSchedule", "DoctorLeave", "DoctorScheduleOverride",
    "Appointment", "OPDQueue",
    "Visit", "Vital", "VisitDiagnosis", "Referral",
    "Drug", "DrugBatch", "Prescription", "PrescriptionItem", "DispenseLog",
    "LabTest", "LabOrder", "LabResult",
    "Service", "Invoice", "InvoiceItem", "Payment",
    "Attachment",
    "Notification",
    "Followup", "Feedback",
    "AuditLog",
]

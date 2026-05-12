# ================================================================
# NexusCare — constants/enums.py
# All status enums, role types, and fixed value sets used
# across the entire application in one place.
# ================================================================

from enum import Enum


# ----------------------------------------------------------------
# HOSPITAL
# ----------------------------------------------------------------

class HospitalStatus(str, Enum):
    """Lifecycle status of a hospital tenant."""
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"


# ----------------------------------------------------------------
# USER & ROLES
# ----------------------------------------------------------------

class UserRole(str, Enum):
    """Built-in system roles. Custom roles are stored in DB."""
    SUPER_ADMIN = "super_admin"       # NexusCare platform admin
    HOSPITAL_ADMIN = "hospital_admin" # Hospital owner/manager
    DOCTOR = "doctor"                 # Treating physician
    NURSE = "nurse"                   # Triage, vitals
    RECEPTIONIST = "receptionist"     # Appointments, queue
    PHARMACIST = "pharmacist"         # Dispensing
    LAB_TECHNICIAN = "lab_technician" # Lab orders, results
    BILLING_STAFF = "billing_staff"   # Invoices, payments


# ----------------------------------------------------------------
# PATIENT
# ----------------------------------------------------------------

class Gender(str, Enum):
    """Patient biological gender options."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class AllergySeverity(str, Enum):
    """Severity level of a patient allergy."""
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    LIFE_THREATENING = "life_threatening"


# ----------------------------------------------------------------
# DOCTOR
# ----------------------------------------------------------------

class LeaveStatus(str, Enum):
    """Approval status of a doctor leave request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DayOfWeek(int, Enum):
    """Day of week for doctor schedules. 0 = Sunday."""
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


# ----------------------------------------------------------------
# APPOINTMENT
# ----------------------------------------------------------------

class AppointmentType(str, Enum):
    """Type of appointment being booked."""
    NEW = "new"
    FOLLOWUP = "followup"
    WALKIN = "walkin"


class AppointmentStatus(str, Enum):
    """Full lifecycle status of an appointment."""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# ----------------------------------------------------------------
# OPD QUEUE
# ----------------------------------------------------------------

class QueuePriority(str, Enum):
    """Priority level of a patient in the OPD queue."""
    NORMAL = "normal"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class QueueStatus(str, Enum):
    """Real-time status of a patient in the OPD queue."""
    WAITING = "waiting"
    CALLED = "called"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    SKIPPED = "skipped"


# ----------------------------------------------------------------
# VISIT
# ----------------------------------------------------------------

class VisitStatus(str, Enum):
    """Lifecycle status of a clinical visit."""
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class DiagnosisType(str, Enum):
    """Type of diagnosis recorded during a visit."""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DIFFERENTIAL = "differential"


class TriageLevel(int, Enum):
    """
    Clinical triage level assessed by nurse.
    1 = Immediate (life threatening)
    2 = Emergent  (could deteriorate rapidly)
    3 = Urgent    (stable but needs prompt care)
    4 = Semi-urgent (stable, can wait)
    5 = Non-urgent  (routine)
    """
    IMMEDIATE = 1
    EMERGENT = 2
    URGENT = 3
    SEMI_URGENT = 4
    NON_URGENT = 5


# ----------------------------------------------------------------
# REFERRAL
# ----------------------------------------------------------------

class ReferralType(str, Enum):
    """Whether referral is within hospital or external."""
    INTERNAL = "internal"
    EXTERNAL = "external"


class ReferralUrgency(str, Enum):
    """How urgently the referral needs to be seen."""
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class ReferralStatus(str, Enum):
    """Lifecycle status of a referral."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    REJECTED = "rejected"


# ----------------------------------------------------------------
# PRESCRIPTION
# ----------------------------------------------------------------

class PrescriptionStatus(str, Enum):
    """Lifecycle status of a prescription."""
    DRAFT = "draft"
    ISSUED = "issued"
    DISPENSED = "dispensed"
    CANCELLED = "cancelled"


class DrugForm(str, Enum):
    """Physical form of a drug."""
    TABLET = "tablet"
    CAPSULE = "capsule"
    SYRUP = "syrup"
    INJECTION = "injection"
    CREAM = "cream"
    DROPS = "drops"
    INHALER = "inhaler"
    SUPPOSITORY = "suppository"
    PATCH = "patch"
    OTHER = "other"


# ----------------------------------------------------------------
# LAB
# ----------------------------------------------------------------

class LabPriority(str, Enum):
    """Priority level of a lab order."""
    ROUTINE = "routine"
    URGENT = "urgent"
    STAT = "stat"           # immediate, life-threatening


class LabOrderStatus(str, Enum):
    """Lifecycle status of a lab order."""
    ORDERED = "ordered"
    COLLECTED = "collected"
    IN_PROGRESS = "in_progress"
    RESULT_READY = "result_ready"
    REVIEWED = "reviewed"
    CANCELLED = "cancelled"


# ----------------------------------------------------------------
# BILLING
# ----------------------------------------------------------------

class ServiceType(str, Enum):
    """Category of a billable service."""
    CONSULTATION = "consultation"
    LAB = "lab"
    DRUG = "drug"
    PROCEDURE = "procedure"
    OTHER = "other"


class InvoiceStatus(str, Enum):
    """Lifecycle status of an invoice."""
    DRAFT = "draft"
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    """Accepted payment methods."""
    CASH = "cash"
    CARD = "card"
    ONLINE = "online"
    INSURANCE = "insurance"
    CHEQUE = "cheque"


# ----------------------------------------------------------------
# NOTIFICATIONS
# ----------------------------------------------------------------

class NotificationChannel(str, Enum):
    """Channel through which a notification is delivered."""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"


# ----------------------------------------------------------------
# ATTACHMENTS
# ----------------------------------------------------------------

class AttachmentEntity(str, Enum):
    """Which entity type an attachment belongs to."""
    PATIENT = "patient"
    VISIT = "visit"
    LAB_ORDER = "lab_order"
    LAB_RESULT = "lab_result"
    INVOICE = "invoice"
    PRESCRIPTION = "prescription"


# ----------------------------------------------------------------
# FOLLOWUP
# ----------------------------------------------------------------

class FollowupStatus(str, Enum):
    """Status of a scheduled follow-up."""
    PENDING = "pending"
    COMPLETED = "completed"
    MISSED = "missed"
    CANCELLED = "cancelled"


# ----------------------------------------------------------------
# AUDIT
# ----------------------------------------------------------------

class AuditAction(str, Enum):
    """Type of action recorded in audit logs."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    VIEW = "VIEW"
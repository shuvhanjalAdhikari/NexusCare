-- ============================================================
-- HOSPITAL OPD SAAS — FINAL SCHEMA (PRODUCTION READY)
-- PostgreSQL 16+
-- Multi-membership design: one global user account, linked to
-- one or more hospitals via hospital_memberships.
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- UTILITY: auto-update updated_at trigger function
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Macro to attach trigger to any table
-- Usage: SELECT attach_updated_at('table_name');
CREATE OR REPLACE FUNCTION attach_updated_at(tbl TEXT)
RETURNS VOID AS $$
BEGIN
  EXECUTE format(
    'CREATE TRIGGER trg_%s_updated_at
     BEFORE UPDATE ON %I
     FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
    tbl, tbl
  );
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 1. CORE TENANCY + ACCESS LAYER
-- ============================================================

CREATE TABLE hospitals (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         VARCHAR(200) NOT NULL,
  slug         VARCHAR(100) UNIQUE NOT NULL,
  logo_url     TEXT,
  address      TEXT,
  phone        VARCHAR(30),
  email        VARCHAR(150),
  timezone     VARCHAR(60) NOT NULL DEFAULT 'UTC',
  plan_id      UUID,                                      -- future: billing plans
  status       VARCHAR(20) NOT NULL DEFAULT 'trial'
                 CHECK (status IN ('active','trial','suspended')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('hospitals');


CREATE TABLE roles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id  UUID REFERENCES hospitals(id) ON DELETE CASCADE, -- NULL = system role
  name         VARCHAR(100) NOT NULL,
  description  TEXT,
  is_custom    BOOLEAN NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('roles');


CREATE TABLE permissions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code         VARCHAR(100) UNIQUE NOT NULL,              -- e.g. 'visits:create'
  module       VARCHAR(80) NOT NULL,                      -- e.g. 'visits', 'billing'
  description  TEXT
);


CREATE TABLE role_permissions (
  role_id       UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);


-- Global user account — not tied to any single hospital.
-- hospital_id and role_id live on hospital_memberships instead.
CREATE TABLE users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  first_name          VARCHAR(100) NOT NULL,
  last_name           VARCHAR(100) NOT NULL,
  email               VARCHAR(150) NOT NULL UNIQUE,       -- globally unique
  password_hash       TEXT NOT NULL,
  phone               VARCHAR(30),
  avatar_url          TEXT,
  system_role         VARCHAR(50)                         -- only set for platform-level accounts
                        CHECK (system_role IS NULL OR system_role IN ('super_admin')),
  is_active           BOOLEAN NOT NULL DEFAULT true,
  email_verified_at   TIMESTAMPTZ,
  last_login_at       TIMESTAMPTZ,
  deleted_at          TIMESTAMPTZ,                        -- soft delete
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('users');


-- Links a user account to a hospital with a role.
-- A user can belong to multiple hospitals; each membership is independent.
-- Soft-deleted to preserve "was a member from X to Y" audit trail.
CREATE TABLE hospital_memberships (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  role_id     UUID NOT NULL REFERENCES roles(id),
  is_active   BOOLEAN NOT NULL DEFAULT true,
  invited_by  UUID REFERENCES users(id),                 -- who added this member
  deleted_at  TIMESTAMPTZ,                               -- soft delete
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, hospital_id)
);
SELECT attach_updated_at('hospital_memberships');
CREATE INDEX idx_memberships_user     ON hospital_memberships(user_id);
CREATE INDEX idx_memberships_hospital ON hospital_memberships(hospital_id);
CREATE INDEX idx_memberships_deleted  ON hospital_memberships(deleted_at) WHERE deleted_at IS NULL;


-- ============================================================
-- 2. PATIENT MODULE
-- ============================================================

CREATE TABLE patients (
  id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id                     UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  patient_number                  VARCHAR(50) NOT NULL,   -- unique per hospital
  first_name                      VARCHAR(100) NOT NULL,
  last_name                       VARCHAR(100) NOT NULL,
  dob                             DATE,
  gender                          VARCHAR(20) CHECK (gender IN ('male','female','other','prefer_not_to_say')),
  blood_group                     VARCHAR(10),
  phone                           VARCHAR(30),
  email                           VARCHAR(150),
  address                         TEXT,
  emergency_contact_name          VARCHAR(150),
  emergency_contact_phone         VARCHAR(30),
  emergency_contact_relationship  VARCHAR(80),
  insurance_provider              VARCHAR(150),
  insurance_policy_number         VARCHAR(100),
  is_active                       BOOLEAN NOT NULL DEFAULT true,
  deleted_at                      TIMESTAMPTZ,            -- soft delete: never hard-delete patients
  created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (hospital_id, patient_number)
);
SELECT attach_updated_at('patients');


CREATE TABLE patient_allergies (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id   UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  hospital_id  UUID NOT NULL REFERENCES hospitals(id),
  allergen     VARCHAR(200) NOT NULL,
  severity     VARCHAR(30) CHECK (severity IN ('mild','moderate','severe','life_threatening')),
  reaction     VARCHAR(200),
  notes        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('patient_allergies');


-- ============================================================
-- 3. DEPARTMENTS + DOCTOR PROFILES
-- ============================================================

CREATE TABLE departments (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id  UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  name         VARCHAR(150) NOT NULL,
  description  TEXT,
  is_active    BOOLEAN NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('departments');


-- One profile per (user, hospital) pair — a doctor can work at multiple hospitals.
CREATE TABLE doctor_profiles (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  hospital_id          UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  department_id        UUID REFERENCES departments(id),
  specialization       VARCHAR(150),
  license_number       VARCHAR(100),
  consultation_fee     NUMERIC(10,2),
  experience_years     SMALLINT,
  bio                  TEXT,
  is_active            BOOLEAN NOT NULL DEFAULT true,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, hospital_id)
);
SELECT attach_updated_at('doctor_profiles');


CREATE TABLE doctor_schedules (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id           UUID NOT NULL REFERENCES hospitals(id),
  doctor_id             UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE,
  day_of_week           SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Sun
  start_time            TIME NOT NULL,
  end_time              TIME NOT NULL,
  slot_duration_minutes SMALLINT NOT NULL DEFAULT 15,
  is_active             BOOLEAN NOT NULL DEFAULT true,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('doctor_schedules');


CREATE TABLE doctor_leaves (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id               UUID NOT NULL REFERENCES hospitals(id),
  doctor_id                 UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE,
  start_date                DATE NOT NULL,
  end_date                  DATE NOT NULL,
  reason                    TEXT,
  status                    VARCHAR(20) NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','approved','rejected')),
  approved_by               UUID REFERENCES users(id),
  approved_by_membership_id UUID REFERENCES hospital_memberships(id),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('doctor_leaves');


CREATE TABLE doctor_schedule_overrides (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id           UUID NOT NULL REFERENCES hospitals(id),
  doctor_id             UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE,
  override_date         DATE NOT NULL,
  start_time            TIME,                             -- NULL = full day blocked
  end_time              TIME,
  slot_duration_minutes SMALLINT,
  reason                VARCHAR(200),
  is_available          BOOLEAN NOT NULL DEFAULT true,    -- false = blocked
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (doctor_id, override_date)
);
SELECT attach_updated_at('doctor_schedule_overrides');


-- ============================================================
-- 4. APPOINTMENTS + OPD QUEUE
-- ============================================================

CREATE TABLE appointments (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id             UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  patient_id              UUID NOT NULL REFERENCES patients(id),
  doctor_id               UUID NOT NULL REFERENCES doctor_profiles(id),
  department_id           UUID REFERENCES departments(id),
  appointment_type        VARCHAR(20) NOT NULL DEFAULT 'new'
                            CHECK (appointment_type IN ('new','followup','walkin')),
  scheduled_at            TIMESTAMPTZ NOT NULL,
  duration_minutes        SMALLINT NOT NULL DEFAULT 15,
  status                  VARCHAR(20) NOT NULL DEFAULT 'scheduled'
                            CHECK (status IN (
                              'scheduled','confirmed','checked_in',
                              'in_consultation','completed','cancelled','no_show'
                            )),
  notes                   TEXT,
  booked_by               UUID REFERENCES users(id),
  booked_by_membership_id UUID REFERENCES hospital_memberships(id),
  deleted_at              TIMESTAMPTZ,                    -- soft delete
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('appointments');


CREATE TABLE opd_queue (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id             UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  appointment_id          UUID REFERENCES appointments(id),   -- nullable for walk-ins
  patient_id              UUID NOT NULL REFERENCES patients(id),
  doctor_id               UUID NOT NULL REFERENCES doctor_profiles(id),
  queue_number            SMALLINT NOT NULL,
  priority                VARCHAR(20) NOT NULL DEFAULT 'normal'
                            CHECK (priority IN ('normal','urgent','emergency')),
  status                  VARCHAR(25) NOT NULL DEFAULT 'waiting'
                            CHECK (status IN (
                              'waiting','called','in_consultation','completed','skipped'
                            )),
  counter_no              VARCHAR(10),
  estimated_wait_minutes  INTEGER,
  checked_in_at           TIMESTAMPTZ,
  called_at               TIMESTAMPTZ,
  completed_at            TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('opd_queue');


-- ============================================================
-- 5. VISIT (CORE CLINICAL LAYER)
-- ============================================================

CREATE TABLE visits (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id                 UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  patient_id                  UUID NOT NULL REFERENCES patients(id),
  doctor_id                   UUID NOT NULL REFERENCES doctor_profiles(id),
  appointment_id              UUID REFERENCES appointments(id),         -- nullable (walk-in)
  queue_id                    UUID REFERENCES opd_queue(id),
  chief_complaint             TEXT,
  history_of_present_illness  TEXT,
  examination_notes           TEXT,
  assessment_notes            TEXT,
  plan_notes                  TEXT,
  status                      VARCHAR(20) NOT NULL DEFAULT 'waiting'
                                CHECK (status IN (
                                  'waiting','active','completed','closed','cancelled'
                                )),
  created_by                  UUID REFERENCES users(id),
  created_by_membership_id    UUID REFERENCES hospital_memberships(id),
  updated_by                  UUID REFERENCES users(id),
  updated_by_membership_id    UUID REFERENCES hospital_memberships(id),
  deleted_at                  TIMESTAMPTZ,                              -- soft delete
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at                TIMESTAMPTZ
);
SELECT attach_updated_at('visits');


CREATE TABLE vitals (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id                  UUID NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  hospital_id               UUID NOT NULL REFERENCES hospitals(id),
  bp_systolic               SMALLINT,
  bp_diastolic              SMALLINT,
  heart_rate                SMALLINT,
  temperature               NUMERIC(4,1),
  spo2                      SMALLINT,
  weight_kg                 NUMERIC(5,1),
  height_cm                 NUMERIC(5,1),
  bmi                       NUMERIC(4,1),
  triage_level              SMALLINT CHECK (triage_level BETWEEN 1 AND 5),
  recorded_by               UUID REFERENCES users(id),
  recorded_by_membership_id UUID REFERENCES hospital_memberships(id),
  recorded_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('vitals');


CREATE TABLE visit_diagnoses (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id       UUID NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  hospital_id    UUID NOT NULL REFERENCES hospitals(id),
  icd_code       VARCHAR(20),
  diagnosis_text VARCHAR(500) NOT NULL,
  type           VARCHAR(20) NOT NULL DEFAULT 'primary'
                   CHECK (type IN ('primary','secondary','differential')),
  is_chronic     BOOLEAN NOT NULL DEFAULT false,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('visit_diagnoses');


CREATE TABLE referrals (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id       UUID NOT NULL REFERENCES hospitals(id),
  visit_id          UUID NOT NULL REFERENCES visits(id),
  from_doctor_id    UUID NOT NULL REFERENCES doctor_profiles(id),
  to_doctor_id      UUID REFERENCES doctor_profiles(id),      -- nullable if external
  to_department_id  UUID REFERENCES departments(id),
  referral_type     VARCHAR(20) NOT NULL
                      CHECK (referral_type IN ('internal','external')),
  external_hospital VARCHAR(200),
  reason            TEXT NOT NULL,
  urgency           VARCHAR(20) NOT NULL DEFAULT 'routine'
                      CHECK (urgency IN ('routine','urgent','emergency')),
  status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','accepted','completed','rejected')),
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('referrals');


-- ============================================================
-- 6. PRESCRIPTION MODULE
-- ============================================================

CREATE TABLE drugs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id   UUID NOT NULL REFERENCES hospitals(id),
  name          VARCHAR(200) NOT NULL,
  generic_name  VARCHAR(200),
  strength      VARCHAR(80),
  form          VARCHAR(80),
  category      VARCHAR(100),
  unit_price    NUMERIC(10,2),
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('drugs');


CREATE TABLE drug_batches (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  drug_id         UUID NOT NULL REFERENCES drugs(id),
  hospital_id     UUID NOT NULL REFERENCES hospitals(id),
  batch_number    VARCHAR(100) NOT NULL,
  expiry_date     DATE NOT NULL,
  stock_quantity  INTEGER NOT NULL DEFAULT 0,
  supplier_name   VARCHAR(200),
  purchase_date   DATE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('drug_batches');


CREATE TABLE prescriptions (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id             UUID NOT NULL REFERENCES hospitals(id),
  visit_id                UUID NOT NULL REFERENCES visits(id),
  patient_id              UUID NOT NULL REFERENCES patients(id),
  doctor_id               UUID NOT NULL REFERENCES doctor_profiles(id),
  status                  VARCHAR(20) NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft','issued','dispensed','cancelled')),
  notes                   TEXT,
  created_by              UUID REFERENCES users(id),
  created_by_membership_id UUID REFERENCES hospital_memberships(id),
  updated_by              UUID REFERENCES users(id),
  updated_by_membership_id UUID REFERENCES hospital_memberships(id),
  issued_at               TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('prescriptions');


CREATE TABLE prescription_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prescription_id UUID NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
  hospital_id     UUID NOT NULL REFERENCES hospitals(id),
  drug_id         UUID NOT NULL REFERENCES drugs(id),
  dose            VARCHAR(80),
  frequency       VARCHAR(80),
  route           VARCHAR(80),
  duration_days   SMALLINT,
  instructions    TEXT,
  quantity        INTEGER,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('prescription_items');


CREATE TABLE dispense_logs (
  id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id                UUID NOT NULL REFERENCES hospitals(id),
  prescription_item_id       UUID NOT NULL REFERENCES prescription_items(id),
  batch_id                   UUID NOT NULL REFERENCES drug_batches(id),
  quantity_dispensed         INTEGER NOT NULL CHECK (quantity_dispensed > 0),
  dispensed_by               UUID NOT NULL REFERENCES users(id),
  dispensed_by_membership_id UUID REFERENCES hospital_memberships(id),
  dispensed_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  notes                      TEXT
);


-- ============================================================
-- 7. LAB MODULE
-- ============================================================

CREATE TABLE lab_tests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id     UUID NOT NULL REFERENCES hospitals(id),
  name            VARCHAR(150) NOT NULL,
  category        VARCHAR(100),
  sample_type     VARCHAR(80),
  tat_hours       SMALLINT,
  reference_range TEXT,
  unit            VARCHAR(40),
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('lab_tests');


CREATE TABLE lab_orders (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id              UUID NOT NULL REFERENCES hospitals(id),
  visit_id                 UUID NOT NULL REFERENCES visits(id),
  patient_id               UUID NOT NULL REFERENCES patients(id),
  doctor_id                UUID NOT NULL REFERENCES doctor_profiles(id),
  test_id                  UUID NOT NULL REFERENCES lab_tests(id),
  priority                 VARCHAR(20) NOT NULL DEFAULT 'routine'
                             CHECK (priority IN ('routine','urgent','stat')),
  status                   VARCHAR(25) NOT NULL DEFAULT 'ordered'
                             CHECK (status IN (
                               'ordered','collected','in_progress',
                               'result_ready','reviewed','cancelled'
                             )),
  sample_collected_at      TIMESTAMPTZ,
  result_ready_at          TIMESTAMPTZ,
  created_by               UUID REFERENCES users(id),
  created_by_membership_id UUID REFERENCES hospital_memberships(id),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('lab_orders');


CREATE TABLE lab_results (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lab_order_id                UUID NOT NULL UNIQUE REFERENCES lab_orders(id) ON DELETE CASCADE,
  hospital_id                 UUID NOT NULL REFERENCES hospitals(id),
  result_value                TEXT,
  unit                        VARCHAR(40),
  reference_range             TEXT,
  is_abnormal                 BOOLEAN NOT NULL DEFAULT false,
  file_url                    TEXT,
  notes                       TEXT,
  uploaded_by                 UUID REFERENCES users(id),
  uploaded_by_membership_id   UUID REFERENCES hospital_memberships(id),
  reviewed_by                 UUID REFERENCES users(id),
  reviewed_by_membership_id   UUID REFERENCES hospital_memberships(id),
  reviewed_at                 TIMESTAMPTZ,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('lab_results');


-- ============================================================
-- 8. BILLING MODULE
-- ============================================================

CREATE TABLE services (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id    UUID NOT NULL REFERENCES hospitals(id),
  department_id  UUID REFERENCES departments(id),
  name           VARCHAR(200) NOT NULL,
  type           VARCHAR(30) NOT NULL
                   CHECK (type IN ('consultation','lab','drug','procedure','other')),
  price          NUMERIC(10,2) NOT NULL,
  is_active      BOOLEAN NOT NULL DEFAULT true,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('services');


CREATE TABLE invoices (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id             UUID NOT NULL REFERENCES hospitals(id),
  patient_id              UUID NOT NULL REFERENCES patients(id),
  appointment_id          UUID REFERENCES appointments(id),
  visit_id                UUID REFERENCES visits(id),
  status                  VARCHAR(20) NOT NULL DEFAULT 'draft'
                            CHECK (status IN (
                              'draft','unpaid','partial','paid',
                              'overdue','void','refunded'
                            )),
  subtotal                NUMERIC(10,2) NOT NULL DEFAULT 0,
  discount_amount         NUMERIC(10,2) NOT NULL DEFAULT 0,
  tax_amount              NUMERIC(10,2) NOT NULL DEFAULT 0,
  total_amount            NUMERIC(10,2) NOT NULL DEFAULT 0,
  due_date                DATE,
  paid_at                 TIMESTAMPTZ,
  created_by              UUID REFERENCES users(id),
  created_by_membership_id UUID REFERENCES hospital_memberships(id),
  updated_by              UUID REFERENCES users(id),
  updated_by_membership_id UUID REFERENCES hospital_memberships(id),
  deleted_at              TIMESTAMPTZ,                    -- soft delete
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('invoices');


CREATE TABLE invoice_items (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id   UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  hospital_id  UUID NOT NULL REFERENCES hospitals(id),
  service_id   UUID REFERENCES services(id),
  description  VARCHAR(300) NOT NULL,
  quantity     SMALLINT NOT NULL DEFAULT 1,
  unit_price   NUMERIC(10,2) NOT NULL,
  total_price  NUMERIC(10,2) NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('invoice_items');


CREATE TABLE payments (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id                UUID NOT NULL REFERENCES invoices(id),
  hospital_id               UUID NOT NULL REFERENCES hospitals(id),
  amount                    NUMERIC(10,2) NOT NULL,
  method                    VARCHAR(30) NOT NULL
                              CHECK (method IN ('cash','card','online','insurance','cheque')),
  reference                 VARCHAR(200),
  recorded_by               UUID REFERENCES users(id),
  recorded_by_membership_id UUID REFERENCES hospital_memberships(id),
  paid_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 9. ATTACHMENTS
-- ============================================================

CREATE TABLE attachments (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id               UUID NOT NULL REFERENCES hospitals(id),
  entity_type               VARCHAR(50) NOT NULL
                              CHECK (entity_type IN (
                                'patient','visit','lab_order','lab_result',
                                'invoice','prescription'
                              )),
  entity_id                 UUID NOT NULL,
  file_url                  TEXT NOT NULL,
  file_name                 VARCHAR(255),
  file_type                 VARCHAR(80),
  file_size_kb              INTEGER,
  description               TEXT,
  uploaded_by               UUID REFERENCES users(id),
  uploaded_by_membership_id UUID REFERENCES hospital_memberships(id),
  uploaded_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attachments_entity ON attachments(entity_type, entity_id);


-- ============================================================
-- 10. FOLLOW-UP SYSTEM
-- ============================================================

CREATE TABLE followups (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id      UUID NOT NULL REFERENCES hospitals(id),
  patient_id       UUID NOT NULL REFERENCES patients(id),
  visit_id         UUID NOT NULL REFERENCES visits(id),
  doctor_id        UUID NOT NULL REFERENCES doctor_profiles(id),
  recommended_date DATE NOT NULL,
  status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','completed','missed','cancelled')),
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT attach_updated_at('followups');


-- ============================================================
-- 11. FEEDBACK
-- ============================================================

CREATE TABLE feedback (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id        UUID NOT NULL REFERENCES hospitals(id),
  patient_id         UUID NOT NULL REFERENCES patients(id),
  appointment_id     UUID REFERENCES appointments(id),
  doctor_id          UUID REFERENCES doctor_profiles(id),
  rating_overall     SMALLINT CHECK (rating_overall BETWEEN 1 AND 5),
  rating_doctor      SMALLINT CHECK (rating_doctor BETWEEN 1 AND 5),
  rating_wait_time   SMALLINT CHECK (rating_wait_time BETWEEN 1 AND 5),
  rating_cleanliness SMALLINT CHECK (rating_cleanliness BETWEEN 1 AND 5),
  comment            TEXT,
  is_anonymous       BOOLEAN NOT NULL DEFAULT false,
  submitted_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 12. SYSTEM MODULE
-- ============================================================

-- Notifications are system-generated and targeted to a user.
-- hospital_id already scopes them; no membership_id needed here.
CREATE TABLE notifications (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id  UUID NOT NULL REFERENCES hospitals(id),
  user_id      UUID REFERENCES users(id),
  type         VARCHAR(80) NOT NULL,
  title        VARCHAR(200) NOT NULL,
  body         TEXT,
  channel      VARCHAR(30) NOT NULL
                 CHECK (channel IN ('in_app','email','sms','whatsapp','push')),
  is_read      BOOLEAN NOT NULL DEFAULT false,
  sent_at      TIMESTAMPTZ,
  read_at      TIMESTAMPTZ,
  metadata     JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE audit_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id   UUID NOT NULL REFERENCES hospitals(id),
  user_id       UUID REFERENCES users(id),
  membership_id UUID REFERENCES hospital_memberships(id),  -- which role/hospital context
  action        VARCHAR(50) NOT NULL,                      -- CREATE/UPDATE/DELETE/LOGIN
  resource_type VARCHAR(80) NOT NULL,
  resource_id   UUID,
  old_value     JSONB,
  new_value     JSONB,
  ip_address    INET,
  user_agent    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- KEY INDEXES FOR QUERY PERFORMANCE
-- ============================================================

-- Multi-tenant isolation (every major query starts with hospital_id)
CREATE INDEX idx_patients_hospital         ON patients(hospital_id);
CREATE INDEX idx_appointments_hospital     ON appointments(hospital_id);
CREATE INDEX idx_appointments_doctor_date  ON appointments(doctor_id, scheduled_at);
CREATE INDEX idx_opd_queue_hospital_date   ON opd_queue(hospital_id, created_at);
CREATE INDEX idx_visits_patient            ON visits(patient_id);
CREATE INDEX idx_visits_doctor             ON visits(doctor_id);
CREATE INDEX idx_lab_orders_visit          ON lab_orders(visit_id);
CREATE INDEX idx_prescriptions_visit       ON prescriptions(visit_id);
CREATE INDEX idx_invoices_patient          ON invoices(patient_id);
CREATE INDEX idx_audit_logs_resource       ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_notifications_user        ON notifications(user_id, is_read);

-- Soft delete: filter out deleted rows efficiently
CREATE INDEX idx_users_deleted             ON users(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_patients_deleted          ON patients(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_appointments_deleted      ON appointments(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_visits_deleted            ON visits(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_invoices_deleted          ON invoices(deleted_at) WHERE deleted_at IS NULL;

-- ============================================================
-- END OF SCHEMA
-- Total tables: 36 (added hospital_memberships)
-- ============================================================

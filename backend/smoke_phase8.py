"""
Phase 8 end-to-end smoke test — Visits + Vitals + Diagnoses + Referrals.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Test cases (printed [PASS] / [FAIL]) — per the approved Phase 8 plan:
   1.  Bootstrap hospital A + admin + 2 doctors (A with a Mon-Fri
       schedule) + a patient + one appointment.
   2.  Create a visit linked to the appointment → 201, status
       'waiting', created_by + created_by_membership_id populated.
       Plus: appointment_id with a mismatched patient → 400.
   3.  GET visit detail → empty vitals / diagnoses / referrals.
   4.  Record 2 vitals — BMI auto-computed when weight + height given.
   5.  GET vitals list → 2 entries in recorded_at order.
   6.  PATCH one vital (BMI recomputed), DELETE the other → list of 1.
   7.  Add 2 diagnoses (primary + secondary).
   8.  PATCH visit status waiting→active→completed; completed_at set.
   9.  Invalid transition completed→active → 400.
   10. Create an internal referral (Dr A → Dr B) during the visit →
       201, status 'pending', from_doctor_id == Dr A. Plus: external
       referral carrying to_doctor_id → 422; internal referral to a
       non-existent doctor → 404.
   11. PATCH referral pending→accepted→completed; invalid
       completed→accepted → 400. GET /referrals includes it.
   12. Cross-tenant: hospital B cannot read/patch A's visit, list A's
       vitals, or read A's referral → 404; B's lists are empty.
   13. Soft-delete the visit → GET visit → 404; the referral is
       excluded from GET /referrals and 404s on direct GET (orphaned).
   14. Demote the test user back to non-super.
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.database import AsyncSessionLocal  # noqa: F401 — ensures models register
from app.utils.security import hash_password


DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"
SEED_HOSPITAL_SLUG = "smoke8-platform"


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


async def _seed_super_admin(pg: asyncpg.Connection) -> None:
    """Idempotently seed a usable super_admin fixture + a throwaway
    workspace so it can obtain a scoped access token."""
    pw_hash = hash_password(TEST_USER_PASSWORD)

    hospital_id = await pg.fetchval(
        "SELECT id FROM hospitals WHERE slug = $1", SEED_HOSPITAL_SLUG
    )
    if hospital_id is None:
        hospital_id = await pg.fetchval(
            "INSERT INTO hospitals (name, slug, timezone) "
            "VALUES ('Smoke8 Platform', $1, 'UTC') RETURNING id",
            SEED_HOSPITAL_SLUG,
        )

    role_id = await pg.fetchval(
        "SELECT id FROM roles WHERE hospital_id = $1 AND name = 'hospital_admin'",
        hospital_id,
    )
    if role_id is None:
        role_id = await pg.fetchval(
            "INSERT INTO roles (hospital_id, name) "
            "VALUES ($1, 'hospital_admin') RETURNING id",
            hospital_id,
        )

    user_id = await pg.fetchval(
        "SELECT id FROM users WHERE email = $1", TEST_USER_EMAIL
    )
    if user_id is None:
        user_id = await pg.fetchval(
            "INSERT INTO users (id, first_name, last_name, email, password_hash, "
            "system_role, is_active) "
            "VALUES ($1, 'Smoke', 'Tester', $2, $3, 'super_admin', true) "
            "RETURNING id",
            uuid.uuid4(), TEST_USER_EMAIL, pw_hash,
        )
    else:
        await pg.execute(
            "UPDATE users SET system_role='super_admin', password_hash=$2, "
            "is_active=true, deleted_at=NULL WHERE id=$1",
            user_id, pw_hash,
        )

    membership_id = await pg.fetchval(
        "SELECT id FROM hospital_memberships WHERE user_id=$1 AND hospital_id=$2",
        user_id, hospital_id,
    )
    if membership_id is None:
        await pg.execute(
            "INSERT INTO hospital_memberships "
            "(user_id, hospital_id, role_id, is_active) "
            "VALUES ($1, $2, $3, true)",
            user_id, hospital_id, role_id,
        )
    else:
        await pg.execute(
            "UPDATE hospital_memberships SET is_active=true, deleted_at=NULL, "
            "role_id=$2 WHERE id=$1",
            membership_id, role_id,
        )


async def _bootstrap_hospital(c: httpx.AsyncClient, super_hdrs: dict, label: str):
    """Create a fresh hospital + admin; return (hospital_id, admin headers)."""
    slug = f"smoke8-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase8 {label.title()}",
            "slug": slug,
            "timezone": "Asia/Kathmandu",
            "admin_email": admin_email,
            "admin_first_name": "Smoke",
            "admin_last_name": label.title(),
        },
        headers=super_hdrs,
    )
    assert r.status_code == 201, f"bootstrap {label}: {r.status_code} {r.text[:200]}"
    body = r.json()
    hospital_id = body["hospital"]["id"]
    invite_token = body["invite_token"]

    r = await c.post(
        "/api/v1/auth/accept-invite",
        json={"invite_token": invite_token, "password": admin_password},
    )
    assert r.status_code == 200, f"accept-invite {label}: {r.text[:200]}"

    r = await c.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": admin_password},
    )
    assert r.status_code == 200, f"login {label}: {r.text[:200]}"
    sel_token = r.json()["selection_token"]

    r = await c.post(
        "/api/v1/auth/select-workspace",
        json={"hospital_id": hospital_id},
        headers={"Authorization": f"Bearer {sel_token}"},
    )
    assert r.status_code == 200, f"select-workspace {label}: {r.text[:200]}"
    access = r.json()["access_token"]
    return hospital_id, {"Authorization": f"Bearer {access}"}


async def _role_id(c: httpx.AsyncClient, hdrs: dict, role_name: str) -> str:
    r = await c.get("/api/v1/roles", headers=hdrs)
    assert r.status_code == 200, f"list roles: {r.text[:200]}"
    for role in r.json():
        if role["name"] == role_name:
            return role["id"]
    raise AssertionError(f"role '{role_name}' not found")


async def _make_doctor(c: httpx.AsyncClient, hdrs: dict, label: str) -> str:
    """Invite + accept a doctor user, then create their doctor profile;
    return the doctor_profile id."""
    role_id = await _role_id(c, hdrs, "doctor")
    email = f"{label}-{uuid.uuid4().hex[:8]}@smoke.dev"
    r = await c.post(
        "/api/v1/users/invite",
        json={
            "email": email,
            "first_name": label.title(),
            "last_name": "Smoke",
            "role_id": role_id,
        },
        headers=hdrs,
    )
    assert r.status_code == 201, f"invite {label}: {r.status_code} {r.text[:200]}"
    body = r.json()
    if body.get("invite_token"):
        ra = await c.post(
            "/api/v1/auth/accept-invite",
            json={"invite_token": body["invite_token"], "password": "Doctor1!"},
        )
        assert ra.status_code == 200, f"accept {label}: {ra.text[:200]}"
    user_id = body["user_id"]

    r = await c.post(
        "/api/v1/doctors",
        json={"user_id": user_id, "specialization": "General Medicine"},
        headers=hdrs,
    )
    assert r.status_code == 201, f"create doctor {label}: {r.text[:200]}"
    return r.json()["id"]


def _next_weekday(start: date, weekday: int) -> date:
    """Next date strictly after `start` whose weekday() == weekday."""
    ahead = (weekday - start.weekday()) % 7
    if ahead == 0:
        ahead = 7
    return start + timedelta(days=ahead)


def _dt(d: date, hour: int, minute: int = 0) -> str:
    """A naive ISO datetime — the API localizes it to the hospital tz."""
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"


async def main() -> None:
    pg = await asyncpg.connect(DB_URL)
    try:
        await _seed_super_admin(pg)
        await _say(True, "super_admin test user + seed workspace ready")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            )
            assert r.status_code == 200, r.text[:200]
            sel_token = r.json()["selection_token"]
            workspace_hid = r.json()["memberships"][0]["hospital_id"]
            r = await c.post(
                "/api/v1/auth/select-workspace",
                json={"hospital_id": workspace_hid},
                headers={"Authorization": f"Bearer {sel_token}"},
            )
            assert r.status_code == 200, r.text[:200]
            super_hdrs = {"Authorization": f"Bearer {r.json()['access_token']}"}

            # ============================================================
            # 1. Bootstrap hospital A + 2 doctors + patient + appointment
            # ============================================================
            hospital_a, hdrs_a = await _bootstrap_hospital(c, super_hdrs, "a")

            doctor_a = await _make_doctor(c, hdrs_a, "drhouse")
            doctor_b = await _make_doctor(c, hdrs_a, "drwilson")

            # Doctor A: Mon-Fri 09:00-17:00, 15-min slots (to book a slot).
            for dow in (1, 2, 3, 4, 5):
                r = await c.post(
                    f"/api/v1/doctors/{doctor_a}/schedules",
                    json={
                        "day_of_week": dow,
                        "start_time": "09:00:00",
                        "end_time": "17:00:00",
                        "slot_duration_minutes": 15,
                    },
                    headers=hdrs_a,
                )
                assert r.status_code == 201, f"schedule dow={dow}: {r.text[:200]}"

            r = await c.post(
                "/api/v1/patients",
                json={"first_name": "Patient", "last_name": "Eight"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create patient: {r.text[:200]}"
            patient_a = r.json()["id"]

            r = await c.post(
                "/api/v1/patients",
                json={"first_name": "Other", "last_name": "Patient"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create patient2: {r.text[:200]}"
            patient_other = r.json()["id"]

            monday = _next_weekday(date.today(), 0)
            r = await c.post(
                "/api/v1/appointments",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "scheduled_at": _dt(monday, 9, 0),
                    "appointment_type": "new",
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"book appointment: {r.text[:200]}"
            appointment_a = r.json()["id"]
            await _say(True, "1. hospital A + 2 doctors + patient + appointment ready")

            # ============================================================
            # 2. Create a visit linked to the appointment
            # ============================================================
            r = await c.post(
                "/api/v1/visits",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "appointment_id": appointment_a,
                    "chief_complaint": "Persistent cough",
                },
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["status"] == "waiting"
                and body["created_by"] is not None
                and body["created_by_membership_id"] is not None,
                f"2. create visit → {r.status_code}, status={body.get('status')}, "
                f"created_by populated",
            )
            visit_a = body["id"]

            # appointment_id with a mismatched patient → 400.
            r = await c.post(
                "/api/v1/visits",
                json={
                    "patient_id": patient_other,
                    "doctor_id": doctor_a,
                    "appointment_id": appointment_a,
                },
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"2b. visit with mismatched appointment patient → {r.status_code}",
            )

            # ============================================================
            # 3. GET visit detail — empty nested collections
            # ============================================================
            r = await c.get(f"/api/v1/visits/{visit_a}", headers=hdrs_a)
            body = r.json()
            await _say(
                r.status_code == 200
                and body["vitals"] == []
                and body["diagnoses"] == []
                and body["referrals"] == [],
                f"3. GET visit detail → empty vitals/diagnoses/referrals",
            )

            # ============================================================
            # 4. Record 2 vitals — BMI auto-computed
            # ============================================================
            r = await c.post(
                f"/api/v1/visits/{visit_a}/vitals",
                json={
                    "bp_systolic": 120,
                    "bp_diastolic": 80,
                    "weight_kg": 70,
                    "height_cm": 175,
                    "triage_level": 3,
                },
                headers=hdrs_a,
            )
            body = r.json()
            # 70 / (1.75^2) = 22.857... → 22.9
            await _say(
                r.status_code == 201 and float(body["bmi"]) == 22.9,
                f"4a. vital #1 → bmi auto-computed = {body.get('bmi')} (expected 22.9)",
            )
            vital_1 = body["id"]

            r = await c.post(
                f"/api/v1/visits/{visit_a}/vitals",
                json={"heart_rate": 88, "spo2": 97},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201 and body["bmi"] is None,
                f"4b. vital #2 (no weight/height) → bmi is null",
            )
            vital_2 = body["id"]

            # ============================================================
            # 5. GET vitals list → 2 entries
            # ============================================================
            r = await c.get(f"/api/v1/visits/{visit_a}/vitals", headers=hdrs_a)
            await _say(
                r.status_code == 200 and len(r.json()) == 2,
                f"5. GET vitals → {len(r.json())} entries",
            )

            # ============================================================
            # 6. PATCH one vital (BMI recomputed), DELETE the other
            # ============================================================
            r = await c.patch(
                f"/api/v1/visits/{visit_a}/vitals/{vital_1}",
                json={"weight_kg": 80},
                headers=hdrs_a,
            )
            body = r.json()
            # 80 / (1.75^2) = 26.122... → 26.1
            await _say(
                r.status_code == 200 and float(body["bmi"]) == 26.1,
                f"6a. PATCH vital #1 weight=80 → bmi recomputed = {body.get('bmi')} "
                f"(expected 26.1)",
            )
            r = await c.delete(
                f"/api/v1/visits/{visit_a}/vitals/{vital_2}", headers=hdrs_a
            )
            assert r.status_code == 204, f"delete vital_2: {r.status_code}"
            r = await c.get(f"/api/v1/visits/{visit_a}/vitals", headers=hdrs_a)
            await _say(
                r.status_code == 200 and len(r.json()) == 1
                and r.json()[0]["id"] == vital_1,
                f"6b. after delete → {len(r.json())} vital remaining",
            )

            # ============================================================
            # 7. Add 2 diagnoses (primary + secondary)
            # ============================================================
            r = await c.post(
                f"/api/v1/visits/{visit_a}/diagnoses",
                json={
                    "diagnosis_text": "Acute bronchitis",
                    "diagnosis_type": "primary",
                    "icd_code": "J20.9",
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"diagnosis 1: {r.text[:200]}"
            r = await c.post(
                f"/api/v1/visits/{visit_a}/diagnoses",
                json={
                    "diagnosis_text": "Essential hypertension",
                    "diagnosis_type": "secondary",
                    "is_chronic": True,
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"diagnosis 2: {r.text[:200]}"
            r = await c.get(f"/api/v1/visits/{visit_a}/diagnoses", headers=hdrs_a)
            types = sorted(d["diagnosis_type"] for d in r.json())
            await _say(
                r.status_code == 200 and types == ["primary", "secondary"],
                f"7. 2 diagnoses recorded → types={types}",
            )

            # ============================================================
            # 8. PATCH visit status waiting→active→completed
            # ============================================================
            r = await c.patch(
                f"/api/v1/visits/{visit_a}",
                json={"status": "active"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "active",
                f"8a. visit waiting→active → {r.status_code}",
            )
            r = await c.patch(
                f"/api/v1/visits/{visit_a}",
                json={"status": "completed", "plan_notes": "Rest + fluids"},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 200 and body["status"] == "completed"
                and body["completed_at"] is not None,
                f"8b. visit active→completed → completed_at set",
            )

            # ============================================================
            # 9. Invalid transition completed→active → 400
            # ============================================================
            r = await c.patch(
                f"/api/v1/visits/{visit_a}",
                json={"status": "active"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"9. invalid transition completed→active → {r.status_code}",
            )

            # ============================================================
            # 10. Create an internal referral (Dr A → Dr B)
            # ============================================================
            r = await c.post(
                f"/api/v1/visits/{visit_a}/referrals",
                json={
                    "referral_type": "internal",
                    "to_doctor_id": doctor_b,
                    "reason": "Cardiology evaluation for hypertension",
                    "urgency": "routine",
                },
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201 and body["status"] == "pending"
                and body["from_doctor_id"] == doctor_a
                and body["to_doctor_id"] == doctor_b,
                f"10a. internal referral A→B → {r.status_code}, status=pending",
            )
            referral_a = body["id"]

            # External referral carrying to_doctor_id → 422 (schema validator).
            r = await c.post(
                f"/api/v1/visits/{visit_a}/referrals",
                json={
                    "referral_type": "external",
                    "to_doctor_id": doctor_b,
                    "external_hospital": "City General",
                    "reason": "MRI not available on-site",
                },
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 422,
                f"10b. external referral with to_doctor_id → {r.status_code}",
            )

            # Internal referral to a non-existent doctor → 404.
            r = await c.post(
                f"/api/v1/visits/{visit_a}/referrals",
                json={
                    "referral_type": "internal",
                    "to_doctor_id": str(uuid.uuid4()),
                    "reason": "Phantom doctor",
                },
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 404,
                f"10c. internal referral to unknown doctor → {r.status_code}",
            )

            # ============================================================
            # 11. PATCH referral pending→accepted→completed
            # ============================================================
            r = await c.patch(
                f"/api/v1/referrals/{referral_a}",
                json={"status": "accepted"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "accepted",
                f"11a. referral pending→accepted → {r.status_code}",
            )
            r = await c.patch(
                f"/api/v1/referrals/{referral_a}",
                json={"status": "completed", "notes": "Seen, BP managed"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "completed",
                f"11b. referral accepted→completed → {r.status_code}",
            )
            r = await c.patch(
                f"/api/v1/referrals/{referral_a}",
                json={"status": "accepted"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"11c. invalid transition completed→accepted → {r.status_code}",
            )
            r = await c.get("/api/v1/referrals", headers=hdrs_a)
            ids = {x["id"] for x in r.json()["items"]}
            await _say(
                r.status_code == 200 and referral_a in ids,
                f"11d. GET /referrals includes the referral → total={r.json()['total']}",
            )

            # ============================================================
            # 12. Cross-tenant isolation
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")

            r = await c.get(f"/api/v1/visits/{visit_a}", headers=hdrs_b)
            await _say(r.status_code == 404, f"12a. B GET A's visit → {r.status_code}")

            r = await c.patch(
                f"/api/v1/visits/{visit_a}",
                json={"chief_complaint": "hijack"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"12b. B PATCH A's visit → {r.status_code}")

            r = await c.get(f"/api/v1/visits/{visit_a}/vitals", headers=hdrs_b)
            await _say(
                r.status_code == 404, f"12c. B list A's visit vitals → {r.status_code}"
            )

            r = await c.get(f"/api/v1/referrals/{referral_a}", headers=hdrs_b)
            await _say(
                r.status_code == 404, f"12d. B GET A's referral → {r.status_code}"
            )

            r = await c.get("/api/v1/visits", headers=hdrs_b)
            await _say(
                r.status_code == 200 and r.json()["total"] == 0,
                f"12e. B visit list → total={r.json().get('total')}",
            )
            r = await c.get("/api/v1/referrals", headers=hdrs_b)
            await _say(
                r.status_code == 200 and r.json()["total"] == 0,
                f"12f. B referral list → total={r.json().get('total')}",
            )

            # ============================================================
            # 13. Soft-delete the visit → orphan referral excluded
            # ============================================================
            r = await c.delete(f"/api/v1/visits/{visit_a}", headers=hdrs_a)
            await _say(
                r.status_code == 204, f"13a. soft-delete visit → {r.status_code}"
            )
            r = await c.get(f"/api/v1/visits/{visit_a}", headers=hdrs_a)
            await _say(
                r.status_code == 404, f"13b. GET deleted visit → {r.status_code}"
            )
            r = await c.get("/api/v1/referrals", headers=hdrs_a)
            ids = {x["id"] for x in r.json()["items"]}
            await _say(
                r.status_code == 200 and referral_a not in ids,
                f"13c. GET /referrals excludes orphaned referral → "
                f"total={r.json()['total']}",
            )
            r = await c.get(f"/api/v1/referrals/{referral_a}", headers=hdrs_a)
            await _say(
                r.status_code == 404,
                f"13d. GET orphaned referral by id → {r.status_code}",
            )

        # ============================================================
        # 14. Demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "14. test user demoted from super_admin")

        print("\n========== PHASE 8 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 8 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

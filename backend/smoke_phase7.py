"""
Phase 7 end-to-end smoke test — Appointments + OPD Queue.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Hospital A is created with timezone='Asia/Kathmandu' (UTC+05:45) so the
timezone-sensitive paths (slot day-window, queue "today") are exercised
against a non-UTC zone.

Test cases (printed [PASS] / [FAIL]) — per the approved Phase 7 plan:
   1.  Bootstrap hospital A (Asia/Kathmandu) + admin + doctor with a
       Mon-Fri 09:00-17:00 schedule + a registered patient.
   2.  Available slots — Monday → 32 fifteen-minute slots from 09:00.
   3.  Available slots — Sunday → empty (no schedule for that weekday).
   4.  Available slots — approved-leave date → empty.
   5.  Available slots — override is_available=false → empty.
   6.  Available slots — override 10:00-12:00 → 8 slots inside it only.
   7.  Book an appointment in an available slot → 201.
   8.  Book the SAME slot again → 409 (SlotUnavailableError).
   9.  Book on an approved-leave date → 409 (DoctorOnLeaveError).
   10. Available slots after booking → the booked slot is gone.
   11. Check-in (POST /queue with appointment_id) → token #1, appointment
       status flips to checked_in.
   12. PATCH queue → in_consultation; linked appointment syncs.
   13. PATCH queue → completed; linked appointment syncs.
   14. Invalid transition: PATCH appointment status=checked_in → 400.
   15. Walk-in (POST /queue, no appointment_id) → token #2.
   16. GET /queue → entries returned in queue_number order.
   17. GET /queue/next → lowest-numbered waiting entry.
   18. Cancel cascade: PATCH appointment status=cancelled → its queue
       entry becomes skipped (queue_number preserved).
   19. Cancel rejected: cancel an appointment whose queue entry is
       in_consultation → 400.
   20. Cross-tenant: hospital B cannot read/patch A's appointment, A's
       queue entry, or A's slots → 404 / isolated.
   21. today-stats → correct mixed-source counts.
   22. Timezone: a slot booked as 09:00 local is stored as 03:15 UTC
       (09:00 - 05:45); today-stats.date == Kathmandu local date.
   23. Demote the test user back to non-super.
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.database import AsyncSessionLocal  # noqa: F401 — ensures models register
from app.utils.security import hash_password


DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"
SEED_HOSPITAL_SLUG = "smoke7-platform"
KATHMANDU = ZoneInfo("Asia/Kathmandu")


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
            "VALUES ('Smoke7 Platform', $1, 'UTC') RETURNING id",
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
    """Create a fresh hospital (Asia/Kathmandu) + admin; return
    (hospital_id, admin headers)."""
    slug = f"smoke7-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase7 {label.title()}",
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


async def _invite_doctor_user(c: httpx.AsyncClient, hdrs: dict, label: str) -> str:
    """Invite + accept a doctor user; return its user_id."""
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
    return body["user_id"]


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
            # 1. Bootstrap hospital A + doctor + schedule + patient
            # ============================================================
            hospital_a, hdrs_a = await _bootstrap_hospital(c, super_hdrs, "a")

            doc_user_id = await _invite_doctor_user(c, hdrs_a, "drhouse")
            r = await c.post(
                "/api/v1/doctors",
                json={"user_id": doc_user_id, "specialization": "Cardiology"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create doctor: {r.text[:200]}"
            doctor_a = r.json()["id"]

            # Mon-Fri (schema day_of_week 1..5) 09:00-17:00, 15-min slots.
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
                json={"first_name": "Patient", "last_name": "One"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create patient: {r.text[:200]}"
            patient_a = r.json()["id"]
            await _say(True, f"1. hospital A + doctor + Mon-Fri schedule + patient ready")

            # Date fixtures (all future, relative to today).
            today = date.today()
            monday = _next_weekday(today, 0)
            sunday = monday + timedelta(days=6)
            leave_date = monday + timedelta(days=1)      # Tuesday
            block_date = monday + timedelta(days=2)      # Wednesday
            narrow_date = monday + timedelta(days=3)     # Thursday

            # Approved leave covering leave_date.
            r = await c.post(
                f"/api/v1/doctors/{doctor_a}/leaves",
                json={
                    "start_date": leave_date.isoformat(),
                    "end_date": leave_date.isoformat(),
                    "reason": "Conference",
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create leave: {r.text[:200]}"
            leave_id = r.json()["id"]
            r = await c.patch(
                f"/api/v1/doctors/{doctor_a}/leaves/{leave_id}",
                json={"status": "approved"},
                headers=hdrs_a,
            )
            assert r.status_code == 200, f"approve leave: {r.text[:200]}"

            # Full-day block override + narrowed override.
            r = await c.post(
                f"/api/v1/doctors/{doctor_a}/overrides",
                json={"override_date": block_date.isoformat(), "is_available": False},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"block override: {r.text[:200]}"
            r = await c.post(
                f"/api/v1/doctors/{doctor_a}/overrides",
                json={
                    "override_date": narrow_date.isoformat(),
                    "is_available": True,
                    "start_time": "10:00:00",
                    "end_time": "12:00:00",
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"narrow override: {r.text[:200]}"

            # ============================================================
            # 2. Available slots — Monday
            # ============================================================
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={monday.isoformat()}",
                headers=hdrs_a,
            )
            slots = r.json()
            await _say(
                r.status_code == 200 and len(slots) == 32
                and slots[0]["start_time"] == "09:00:00"
                and slots[-1]["end_time"] == "17:00:00",
                f"2. Monday → {len(slots)} slots (09:00..17:00)",
            )

            # ============================================================
            # 3. Available slots — Sunday → empty
            # ============================================================
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={sunday.isoformat()}",
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json() == [],
                f"3. Sunday → {len(r.json())} slots (expected 0)",
            )

            # ============================================================
            # 4. Available slots — approved-leave date → empty
            # ============================================================
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={leave_date.isoformat()}",
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json() == [],
                f"4. leave date → {len(r.json())} slots (expected 0)",
            )

            # ============================================================
            # 5. Available slots — blocked override → empty
            # ============================================================
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={block_date.isoformat()}",
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json() == [],
                f"5. blocked-override date → {len(r.json())} slots (expected 0)",
            )

            # ============================================================
            # 6. Available slots — narrowed override → 8 slots in 10-12
            # ============================================================
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={narrow_date.isoformat()}",
                headers=hdrs_a,
            )
            slots = r.json()
            await _say(
                r.status_code == 200 and len(slots) == 8
                and slots[0]["start_time"] == "10:00:00"
                and slots[-1]["end_time"] == "12:00:00",
                f"6. narrowed override → {len(slots)} slots (10:00..12:00)",
            )

            # ============================================================
            # 7. Book an appointment in an available slot
            # ============================================================
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
            await _say(
                r.status_code == 201 and r.json()["status"] == "scheduled"
                and r.json()["duration_minutes"] == 15,
                f"7. book Monday 09:00 → {r.status_code}",
            )
            appt_main = r.json()["id"]

            # walkin appointment_type must be rejected here.
            r = await c.post(
                "/api/v1/appointments",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "scheduled_at": _dt(monday, 13, 0),
                    "appointment_type": "walkin",
                },
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"7b. appointment_type=walkin rejected → {r.status_code}",
            )

            # ============================================================
            # 8. Double-book the same slot → 409
            # ============================================================
            r = await c.post(
                "/api/v1/appointments",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "scheduled_at": _dt(monday, 9, 0),
                },
                headers=hdrs_a,
            )
            await _say(r.status_code == 409, f"8. double-book 09:00 → {r.status_code}")

            # ============================================================
            # 9. Book on an approved-leave date → 409
            # ============================================================
            r = await c.post(
                "/api/v1/appointments",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "scheduled_at": _dt(leave_date, 10, 0),
                },
                headers=hdrs_a,
            )
            await _say(r.status_code == 409, f"9. book on leave date → {r.status_code}")

            # ============================================================
            # 10. Available slots after booking — 09:00 is gone
            # ============================================================
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={monday.isoformat()}",
                headers=hdrs_a,
            )
            starts = [s["start_time"] for s in r.json()]
            await _say(
                len(starts) == 31 and "09:00:00" not in starts,
                f"10. after booking → {len(starts)} slots, 09:00 removed",
            )

            # Two more appointments for the cancel-cascade tests.
            r = await c.post(
                "/api/v1/appointments",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "scheduled_at": _dt(monday, 9, 15),
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"book appt_cancel: {r.text[:200]}"
            appt_cancel = r.json()["id"]

            r = await c.post(
                "/api/v1/appointments",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "scheduled_at": _dt(monday, 9, 30),
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"book appt_reject: {r.text[:200]}"
            appt_reject = r.json()["id"]

            # ============================================================
            # 11. Check-in appt_main → token #1
            # ============================================================
            r = await c.post(
                "/api/v1/queue",
                json={"appointment_id": appt_main},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 201 and r.json()["queue_number"] == 1
                and r.json()["status"] == "waiting"
                and r.json()["appointment_id"] == appt_main,
                f"11a. check-in → token #{r.json().get('queue_number')}",
            )
            queue_main = r.json()["id"]

            r = await c.get(f"/api/v1/appointments/{appt_main}", headers=hdrs_a)
            await _say(
                r.json()["status"] == "checked_in",
                f"11b. appointment status synced → {r.json()['status']}",
            )

            # ============================================================
            # 12. Queue → in_consultation; appointment syncs
            # ============================================================
            r = await c.patch(
                f"/api/v1/queue/{queue_main}",
                json={"status": "in_consultation"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "in_consultation",
                f"12a. queue → in_consultation → {r.status_code}",
            )
            r = await c.get(f"/api/v1/appointments/{appt_main}", headers=hdrs_a)
            await _say(
                r.json()["status"] == "in_consultation",
                f"12b. appointment synced → {r.json()['status']}",
            )

            # ============================================================
            # 13. Queue → completed; appointment syncs
            # ============================================================
            r = await c.patch(
                f"/api/v1/queue/{queue_main}",
                json={"status": "completed"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "completed"
                and r.json()["completed_at"] is not None,
                f"13a. queue → completed → {r.status_code}",
            )
            r = await c.get(f"/api/v1/appointments/{appt_main}", headers=hdrs_a)
            await _say(
                r.json()["status"] == "completed",
                f"13b. appointment synced → {r.json()['status']}",
            )

            # ============================================================
            # 14. Invalid transition — PATCH appointment → checked_in
            # ============================================================
            r = await c.patch(
                f"/api/v1/appointments/{appt_main}",
                json={"status": "checked_in"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"14. PATCH completed appointment → checked_in → {r.status_code}",
            )

            # ============================================================
            # 15. Walk-in → token #2
            # ============================================================
            r = await c.post(
                "/api/v1/queue",
                json={"patient_id": patient_a, "doctor_id": doctor_a},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 201 and r.json()["queue_number"] == 2
                and r.json()["appointment_id"] is None,
                f"15. walk-in → token #{r.json().get('queue_number')}",
            )
            queue_walkin = r.json()["id"]

            # ============================================================
            # 16. GET /queue — ordered by queue_number
            # ============================================================
            r = await c.get(f"/api/v1/queue?doctor_id={doctor_a}", headers=hdrs_a)
            numbers = [e["queue_number"] for e in r.json()]
            await _say(
                r.status_code == 200 and numbers == sorted(numbers)
                and numbers == [1, 2],
                f"16. GET /queue ordered → {numbers}",
            )

            # ============================================================
            # 17. GET /queue/next — lowest waiting
            # ============================================================
            r = await c.get(
                f"/api/v1/queue/next?doctor_id={doctor_a}", headers=hdrs_a
            )
            await _say(
                r.status_code == 200 and r.json() is not None
                and r.json()["queue_number"] == 2
                and r.json()["status"] == "waiting",
                f"17. /queue/next → token #{r.json() and r.json().get('queue_number')}",
            )

            # ============================================================
            # 18. Cancel cascade — appointment cancelled → queue skipped
            # ============================================================
            r = await c.post(
                "/api/v1/queue",
                json={"appointment_id": appt_cancel},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"check-in appt_cancel: {r.text[:200]}"
            queue_cancel = r.json()["id"]
            queue_cancel_num = r.json()["queue_number"]

            r = await c.patch(
                f"/api/v1/appointments/{appt_cancel}",
                json={"status": "cancelled"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "cancelled",
                f"18a. cancel appointment → {r.status_code}",
            )
            r = await c.get(
                f"/api/v1/queue?doctor_id={doctor_a}&status=skipped", headers=hdrs_a
            )
            skipped = {e["id"]: e for e in r.json()}
            await _say(
                queue_cancel in skipped
                and skipped[queue_cancel]["queue_number"] == queue_cancel_num,
                f"18b. queue entry cascaded to skipped (token #{queue_cancel_num} kept)",
            )

            # ============================================================
            # 19. Cancel rejected — queue entry in_consultation
            # ============================================================
            r = await c.post(
                "/api/v1/queue",
                json={"appointment_id": appt_reject},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"check-in appt_reject: {r.text[:200]}"
            queue_reject = r.json()["id"]
            r = await c.patch(
                f"/api/v1/queue/{queue_reject}",
                json={"status": "in_consultation"},
                headers=hdrs_a,
            )
            assert r.status_code == 200, f"queue_reject → in_consultation: {r.text[:200]}"

            r = await c.patch(
                f"/api/v1/appointments/{appt_reject}",
                json={"status": "cancelled"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"19. cancel rejected (visit in progress) → {r.status_code}",
            )

            # ============================================================
            # 20. Cross-tenant isolation
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")

            r = await c.get(f"/api/v1/appointments/{appt_main}", headers=hdrs_b)
            await _say(r.status_code == 404, f"20a. B GET A's appointment → {r.status_code}")

            r = await c.patch(
                f"/api/v1/appointments/{appt_main}",
                json={"notes": "hijack"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"20b. B PATCH A's appointment → {r.status_code}")

            r = await c.get("/api/v1/appointments", headers=hdrs_b)
            await _say(
                r.status_code == 200 and r.json()["total"] == 0,
                f"20c. B appointment list → total={r.json().get('total')}",
            )

            r = await c.patch(
                f"/api/v1/queue/{queue_main}",
                json={"status": "completed"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"20d. B PATCH A's queue entry → {r.status_code}")

            r = await c.get("/api/v1/queue", headers=hdrs_b)
            await _say(
                r.status_code == 200 and r.json() == [],
                f"20e. B queue list → {len(r.json())} entries",
            )

            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/available-slots?date={monday.isoformat()}",
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"20f. B GET A's doctor slots → {r.status_code}")

            # ============================================================
            # 21. today-stats — mixed-source counts
            # ============================================================
            # Queue today for doctor A: #1 completed, #2 walk-in waiting,
            # #3 skipped (cascade), #4 in_consultation.
            r = await c.get(
                f"/api/v1/doctors/{doctor_a}/today-stats", headers=hdrs_a
            )
            stats = r.json()
            await _say(
                r.status_code == 200
                and stats["total_in_queue"] == 4
                and stats["waiting"] == 1
                and stats["called"] == 0
                and stats["in_consultation"] == 1
                and stats["completed"] == 1
                and stats["skipped"] == 1
                and stats["walk_ins"] == 1
                and stats["no_show"] == 0,
                f"21. today-stats → {stats}",
            )

            # ============================================================
            # 22. Timezone — Asia/Kathmandu (UTC+05:45)
            # ============================================================
            r = await c.get(f"/api/v1/appointments/{appt_main}", headers=hdrs_a)
            scheduled_at = datetime.fromisoformat(r.json()["scheduled_at"])
            local = scheduled_at.astimezone(KATHMANDU)
            utc = scheduled_at.astimezone(ZoneInfo("UTC"))
            await _say(
                local.hour == 9 and local.minute == 0
                and utc.hour == 3 and utc.minute == 15,
                f"22a. 09:00 Kathmandu stored as {utc.hour:02d}:{utc.minute:02d} UTC",
            )
            await _say(
                stats["date"] == datetime.now(KATHMANDU).date().isoformat(),
                f"22b. today-stats.date == Kathmandu local date ({stats['date']})",
            )

        # ============================================================
        # 23. Demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "23. test user demoted from super_admin")

        print("\n========== PHASE 7 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 7 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

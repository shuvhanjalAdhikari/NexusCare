"""
Phase 12 end-to-end smoke test — Notifications + Follow-ups + Feedback.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Test cases (printed [PASS] / [FAIL]) — per the approved Phase 12 plan:
   1.  Bootstrap hospital A + admin + doctor + patient + active visit.
   2.  Schedule a follow-up: POST /visits/{id}/followups → 'pending'.
   3.  GET /followups returns it; ?patient_id= filter works.
   4.  PATCH follow-up → 'completed'; then 'completed'→'pending' → 400.
   5.  Super-admin POST /api/v1/admin/notifications for A's admin →
       appears in that user's GET /notifications/me.
   6.  GET /notifications/me/unread-count → 1.
   7.  PATCH /me/{id}/read → unread-count back to 0.
   8.  DELETE /me/{id} → no longer in the list.
   9.  POST /feedback full (patient+doctor, ratings, comment) → 201.
   10. POST /feedback anonymous (patient_id + is_anonymous, no doctor) → 201.
   11. GET /feedback?doctor_id= filters; min_rating filter works.
   12. Cross-tenant: hospital B cannot read A's follow-up or feedback → 404.
   13. Cross-user: a second user in hospital A sees an EMPTY /me list
       (200, never 404) while A's admin still sees their notification.
   (cleanup) Demote the test user back to non-super.
"""

import asyncio
import sys
import uuid
from datetime import date, timedelta

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.database import AsyncSessionLocal  # noqa: F401 — ensures models register
from app.utils.security import hash_password


DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"
SEED_HOSPITAL_SLUG = "smoke12-platform"


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
            "VALUES ('Smoke12 Platform', $1, 'UTC') RETURNING id",
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
    """Create a fresh hospital + admin; return (hospital_id, admin headers,
    admin user_id)."""
    slug = f"smoke12-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase12 {label.title()}",
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
    admin_user_id = body["admin_user_id"]
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
    return hospital_id, {"Authorization": f"Bearer {access}"}, admin_user_id


async def _role_id(c: httpx.AsyncClient, hdrs: dict, role_name: str) -> str:
    r = await c.get("/api/v1/roles", headers=hdrs)
    assert r.status_code == 200, f"list roles: {r.text[:200]}"
    for role in r.json():
        if role["name"] == role_name:
            return role["id"]
    raise AssertionError(f"role '{role_name}' not found")


async def _make_member(
    c: httpx.AsyncClient, hdrs: dict, hospital_id: str, role_name: str, label: str
):
    """Invite + accept + login a hospital member; return (user_id, headers)."""
    role_id = await _role_id(c, hdrs, role_name)
    email = f"{label}-{uuid.uuid4().hex[:8]}@smoke.dev"
    password = "Member1!"

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
    user_id = body["user_id"]
    if body.get("invite_token"):
        ra = await c.post(
            "/api/v1/auth/accept-invite",
            json={"invite_token": body["invite_token"], "password": password},
        )
        assert ra.status_code == 200, f"accept {label}: {ra.text[:200]}"

    r = await c.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, f"login {label}: {r.text[:200]}"
    sel_token = r.json()["selection_token"]
    r = await c.post(
        "/api/v1/auth/select-workspace",
        json={"hospital_id": hospital_id},
        headers={"Authorization": f"Bearer {sel_token}"},
    )
    assert r.status_code == 200, f"select-workspace {label}: {r.text[:200]}"
    return user_id, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _make_doctor(c: httpx.AsyncClient, hdrs: dict, hospital_id: str, label: str):
    """Invite a doctor user + create their doctor profile; return profile id."""
    user_id, _ = await _make_member(c, hdrs, hospital_id, "doctor", label)
    r = await c.post(
        "/api/v1/doctors",
        json={"user_id": user_id, "specialization": "General Medicine"},
        headers=hdrs,
    )
    assert r.status_code == 201, f"create doctor {label}: {r.text[:200]}"
    return r.json()["id"]


async def _make_patient(c: httpx.AsyncClient, hdrs: dict) -> str:
    r = await c.post(
        "/api/v1/patients",
        json={"first_name": "Patient", "last_name": "Twelve"},
        headers=hdrs,
    )
    assert r.status_code == 201, f"create patient: {r.text[:200]}"
    return r.json()["id"]


async def _make_visit(
    c: httpx.AsyncClient, hdrs: dict, patient_id: str, doctor_id: str
) -> str:
    """Create a visit and advance it to 'active'."""
    r = await c.post(
        "/api/v1/visits",
        json={
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "chief_complaint": "Cough and fever",
        },
        headers=hdrs,
    )
    assert r.status_code == 201, f"create visit: {r.text[:200]}"
    visit_id = r.json()["id"]
    r = await c.patch(
        f"/api/v1/visits/{visit_id}", json={"status": "active"}, headers=hdrs
    )
    assert r.status_code == 200, f"activate visit: {r.text[:200]}"
    return visit_id


async def main() -> None:
    pg = await asyncpg.connect(DB_URL)
    try:
        await _seed_super_admin(pg)
        await _say(True, "super_admin test user + seed workspace ready")

        return_date = (date.today() + timedelta(days=14)).isoformat()
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
            # 1. Bootstrap hospital A + doctor + patient + active visit
            # ============================================================
            hospital_a, hdrs_a, admin_a_uid = await _bootstrap_hospital(
                c, super_hdrs, "a"
            )
            doctor_a = await _make_doctor(c, hdrs_a, hospital_a, "drcare")
            patient_a = await _make_patient(c, hdrs_a)
            visit_a = await _make_visit(c, hdrs_a, patient_a, doctor_a)
            await _say(
                True,
                "1. hospital A + doctor + patient + active visit ready",
            )

            # ============================================================
            # 2. Schedule a follow-up off the visit → 'pending'
            # ============================================================
            r = await c.post(
                f"/api/v1/visits/{visit_a}/followups",
                json={"recommended_date": return_date,
                      "notes": "Review labs in two weeks"},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["status"] == "pending"
                and body["patient_id"] == patient_a
                and body["visit_id"] == visit_a
                and body["doctor_id"] == doctor_a,
                f"2. POST followup → {r.status_code}, status="
                f"{body.get('status')} (expected 201/pending)",
            )
            followup_a = body["id"]

            # ============================================================
            # 3. GET /followups — returned + patient_id filter works
            # ============================================================
            r = await c.get("/api/v1/followups", headers=hdrs_a)
            all_ids = {f["id"] for f in r.json()["items"]}
            r2 = await c.get(
                f"/api/v1/followups?patient_id={patient_a}", headers=hdrs_a
            )
            filtered_ids = {f["id"] for f in r2.json()["items"]}
            r3 = await c.get(
                f"/api/v1/followups?patient_id={uuid.uuid4()}", headers=hdrs_a
            )
            await _say(
                r.status_code == 200
                and followup_a in all_ids
                and followup_a in filtered_ids
                and len(r3.json()["items"]) == 0,
                f"3. GET /followups lists it; ?patient_id filter works "
                f"({len(all_ids)} total, {len(filtered_ids)} for patient)",
            )

            # ============================================================
            # 4. PATCH status → completed; completed → pending → 400
            # ============================================================
            r = await c.patch(
                f"/api/v1/followups/{followup_a}",
                json={"status": "completed"},
                headers=hdrs_a,
            )
            ok_complete = r.status_code == 200 and r.json()["status"] == "completed"
            r = await c.patch(
                f"/api/v1/followups/{followup_a}",
                json={"status": "pending"},
                headers=hdrs_a,
            )
            await _say(
                ok_complete and r.status_code == 400,
                f"4. followup → completed, then completed→pending → "
                f"{r.status_code} (expected 400)",
            )

            # ============================================================
            # 5. Super-admin POST notification → appears in A admin's /me
            # ============================================================
            r = await c.post(
                "/api/v1/admin/notifications",
                json={
                    "hospital_id": hospital_a,
                    "user_id": admin_a_uid,
                    "type": "lab_result",
                    "title": "Lab result ready",
                    "body": "CBC result is available for review.",
                },
                headers=super_hdrs,
            )
            assert r.status_code == 201, f"admin create notification: {r.text[:200]}"
            notif_a = r.json()["id"]

            r = await c.get("/api/v1/notifications/me", headers=hdrs_a)
            me_ids = {n["id"] for n in r.json()["items"]}
            await _say(
                r.status_code == 200 and notif_a in me_ids,
                f"5. super-admin notification appears in admin's /me "
                f"({len(me_ids)} notification(s))",
            )

            # ============================================================
            # 6. unread-count → 1
            # ============================================================
            r = await c.get(
                "/api/v1/notifications/me/unread-count", headers=hdrs_a
            )
            await _say(
                r.status_code == 200 and r.json()["unread_count"] == 1,
                f"6. unread-count → {r.json().get('unread_count')} (expected 1)",
            )

            # ============================================================
            # 7. Mark read → unread-count back to 0
            # ============================================================
            r = await c.patch(
                f"/api/v1/notifications/me/{notif_a}/read", headers=hdrs_a
            )
            ok_read = r.status_code == 200 and r.json()["is_read"] is True
            r = await c.get(
                "/api/v1/notifications/me/unread-count", headers=hdrs_a
            )
            await _say(
                ok_read and r.json()["unread_count"] == 0,
                f"7. mark-read → unread-count {r.json().get('unread_count')} "
                f"(expected 0)",
            )

            # ============================================================
            # 8. Dismiss → no longer in the list
            # ============================================================
            r = await c.delete(
                f"/api/v1/notifications/me/{notif_a}", headers=hdrs_a
            )
            ok_del = r.status_code == 204
            r = await c.get("/api/v1/notifications/me", headers=hdrs_a)
            me_ids = {n["id"] for n in r.json()["items"]}
            await _say(
                ok_del and notif_a not in me_ids,
                f"8. DELETE notification → {r.status_code if not ok_del else 204}, "
                f"absent from list",
            )

            # ============================================================
            # 9. POST /feedback — full record
            # ============================================================
            r = await c.post(
                "/api/v1/feedback",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "rating_overall": 5,
                    "rating_doctor": 5,
                    "rating_wait_time": 4,
                    "rating_cleanliness": 5,
                    "comment": "Excellent care, short wait.",
                },
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["patient_id"] == patient_a
                and body["doctor_id"] == doctor_a
                and body["rating_overall"] == 5
                and body["is_anonymous"] is False,
                f"9. POST /feedback full → {r.status_code} (expected 201)",
            )
            feedback_full = body["id"]

            # ============================================================
            # 10. POST /feedback — anonymous (patient linked, flagged)
            # ============================================================
            r = await c.post(
                "/api/v1/feedback",
                json={
                    "patient_id": patient_a,
                    "rating_overall": 3,
                    "comment": "Average experience.",
                    "is_anonymous": True,
                },
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["is_anonymous"] is True
                and body["doctor_id"] is None,
                f"10. POST /feedback anonymous → {r.status_code} (expected 201)",
            )

            # ============================================================
            # 11. GET /feedback — doctor + rating filters
            # ============================================================
            r = await c.get(
                f"/api/v1/feedback?doctor_id={doctor_a}", headers=hdrs_a
            )
            by_doctor = {f["id"] for f in r.json()["items"]}
            r2 = await c.get("/api/v1/feedback?min_rating=4", headers=hdrs_a)
            by_rating = {f["id"] for f in r2.json()["items"]}
            await _say(
                r.status_code == 200
                and by_doctor == {feedback_full}
                and feedback_full in by_rating
                and len(by_rating) == 1,
                f"11. GET /feedback filters → doctor={len(by_doctor)}, "
                f"min_rating>=4 → {len(by_rating)} (each expected 1)",
            )

            # ============================================================
            # 12. Cross-tenant — hospital B cannot read A's records
            # ============================================================
            hospital_b, hdrs_b, _ = await _bootstrap_hospital(c, super_hdrs, "b")
            r1 = await c.get(
                f"/api/v1/followups/{followup_a}", headers=hdrs_b
            )
            r2 = await c.get(
                f"/api/v1/feedback/{feedback_full}", headers=hdrs_b
            )
            await _say(
                r1.status_code == 404 and r2.status_code == 404,
                f"12. hospital B reads A's follow-up/feedback → "
                f"{r1.status_code}/{r2.status_code} (expected 404/404)",
            )

            # ============================================================
            # 13. Cross-user — a second user in A sees an EMPTY /me list
            # ============================================================
            # Fresh notification for A's admin (the one in case 5 was
            # dismissed). The second user must NOT see it.
            r = await c.post(
                "/api/v1/admin/notifications",
                json={
                    "hospital_id": hospital_a,
                    "user_id": admin_a_uid,
                    "type": "appointment",
                    "title": "Appointment in 1 hour",
                },
                headers=super_hdrs,
            )
            assert r.status_code == 201, f"refresh notification: {r.text[:200]}"

            _, hdrs_nurse = await _make_member(
                c, hdrs_a, hospital_a, "nurse", "nurse"
            )
            r_nurse = await c.get("/api/v1/notifications/me", headers=hdrs_nurse)
            r_admin = await c.get("/api/v1/notifications/me", headers=hdrs_a)
            await _say(
                r_nurse.status_code == 200
                and len(r_nurse.json()["items"]) == 0
                and r_admin.status_code == 200
                and len(r_admin.json()["items"]) == 1,
                f"13. second user in A → empty /me list "
                f"(status {r_nurse.status_code}, "
                f"{len(r_nurse.json()['items'])} items); admin still sees "
                f"{len(r_admin.json()['items'])}",
            )

        # ============================================================
        # Cleanup — demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "cleanup: test user demoted from super_admin")

        print("\n========== PHASE 12 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 12 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

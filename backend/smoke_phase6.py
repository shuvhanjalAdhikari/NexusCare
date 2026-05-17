"""
Phase 6 end-to-end smoke test — Doctor module.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin for the duration so we can
bootstrap fresh hospitals, then demoted at the end.

Test cases (all printed with [PASS] / [FAIL] prefix) — per plan §8:
   1.  Bootstrap hospital A + admin.
   2.  Invite & accept a doctor user; admin creates a DoctorProfile.
   3.  List + search (?q=, ?specialization=).
   4.  GET one — nested user fields + empty schedules + empty leaves.
   5.  PATCH doctor (specialization, fee).
   6.  Schedule CRUD: add Mon-Fri (5), list, update one, delete one.
   7.  Leave CRUD: request, PATCH -> approved (audit populated), filter.
   8.  Override CRUD: full-day block + half-day; UNIQUE conflict -> 409.
   9.  Cross-tenant: B admin reads/patches/deletes A's doctor -> 404.
   10. Soft-delete doctor (is_active=false) -> list excludes; GET still 200.
   11. Pagination: 25 doctors in B, ?page=2&size=10 -> pages=3, items=10.
   12. Negative validations: bad day_of_week, start>=end, leave start>end,
       non-doctor user_id -> 400/422.
   13. Demote test user back to non-super.
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
SEED_HOSPITAL_SLUG = "smoke6-platform"


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


async def _seed_super_admin(pg: asyncpg.Connection) -> None:
    """
    Idempotently seed a usable super_admin fixture.

    This DB starts completely empty, so the smoke test seeds its own
    fixtures rather than relying on pre-existing data. A super admin
    can only obtain an access token (needed for /api/v1/admin/*) by
    selecting a workspace, which requires at least one membership — so
    we also seed a throwaway hospital + role + membership for the user.
    Safe to re-run: every step is a SELECT-then-INSERT upsert.
    """
    pw_hash = hash_password(TEST_USER_PASSWORD)

    # Seed hospital — status defaults to 'trial' (not suspended), so it is
    # selectable as a workspace.
    hospital_id = await pg.fetchval(
        "SELECT id FROM hospitals WHERE slug = $1", SEED_HOSPITAL_SLUG
    )
    if hospital_id is None:
        hospital_id = await pg.fetchval(
            "INSERT INTO hospitals (name, slug, timezone) "
            "VALUES ('Smoke Platform', $1, 'UTC') RETURNING id",
            SEED_HOSPITAL_SLUG,
        )

    # Seed a role on that hospital for the membership to reference.
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

    # Seed / promote the super_admin user.
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

    # Seed the membership that lets the super admin select a workspace.
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
    """Creates a fresh hospital + admin and returns (hospital_id, admin headers)."""
    slug = f"smoke6-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase6 {label.title()}",
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
    """Returns the role_id for a built-in role visible to this hospital."""
    r = await c.get("/api/v1/roles", headers=hdrs)
    assert r.status_code == 200, f"list roles: {r.text[:200]}"
    for role in r.json():
        if role["name"] == role_name:
            return role["id"]
    raise AssertionError(f"role '{role_name}' not found: {[x['name'] for x in r.json()]}")


async def _invite_user(
    c: httpx.AsyncClient,
    hdrs: dict,
    role_id: str,
    label: str,
    *,
    accept: bool = False,
) -> dict:
    """Invites a fresh user with the given role. Returns {user_id, email, invite_token}.
    If accept=True, the invitee also accepts the invite (sets a password)."""
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
    if accept and body.get("invite_token"):
        ra = await c.post(
            "/api/v1/auth/accept-invite",
            json={"invite_token": body["invite_token"], "password": "Doctor1!"},
        )
        assert ra.status_code == 200, f"accept {label}: {ra.text[:200]}"
    return {"user_id": body["user_id"], "email": body["email"]}


async def main() -> None:
    pg = await asyncpg.connect(DB_URL)
    try:
        # ---- self-seed fixtures (this DB starts empty) ----
        await _seed_super_admin(pg)
        await _say(True, "super_admin test user + seed workspace ready")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # super-admin login + workspace select
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
            # 1. Bootstrap hospital A
            # ============================================================
            hospital_a, hdrs_a = await _bootstrap_hospital(c, super_hdrs, "a")
            await _say(True, f"1. hospital A bootstrapped ({hospital_a})")

            # ============================================================
            # 2. Invite & accept a doctor user; admin creates DoctorProfile
            # ============================================================
            doctor_role_a = await _role_id(c, hdrs_a, "doctor")
            doc_user = await _invite_user(c, hdrs_a, doctor_role_a, "drhouse", accept=True)
            await _say(True, f"2a. doctor user invited + accepted ({doc_user['user_id']})")

            r = await c.post(
                "/api/v1/doctors",
                json={
                    "user_id": doc_user["user_id"],
                    "specialization": "Cardiology",
                    "license_number": "LIC-A-001",
                    "consultation_fee": 500,
                    "experience_years": 12,
                    "bio": "Senior cardiologist.",
                },
                headers=hdrs_a,
            )
            await _say(r.status_code == 201, f"2b. create DoctorProfile -> {r.status_code} {r.text[:160]}")
            doctor_a = r.json()
            await _say(
                doctor_a["user_id"] == doc_user["user_id"]
                and doctor_a["email"] == doc_user["email"]
                and doctor_a["first_name"] == "Drhouse"
                and doctor_a["schedules"] == []
                and doctor_a["active_leaves"] == [],
                "2c. response flattens user fields + empty schedules/leaves",
            )

            # Duplicate create for the same user -> 409, no auto-reactivation
            r = await c.post(
                "/api/v1/doctors",
                json={"user_id": doc_user["user_id"], "specialization": "Dup"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 409, f"2d. duplicate DoctorProfile -> {r.status_code}")

            doctor_a_id = doctor_a["id"]

            # ============================================================
            # 3. List + search
            # ============================================================
            r = await c.get("/api/v1/doctors", headers=hdrs_a)
            await _say(
                r.status_code == 200 and r.json()["total"] == 1,
                f"3a. list -> total={r.json().get('total')}",
            )

            r = await c.get("/api/v1/doctors?q=Drhouse", headers=hdrs_a)
            await _say(r.json()["total"] == 1, "3b. ?q=Drhouse matches first_name")

            r = await c.get("/api/v1/doctors?specialization=Cardiology", headers=hdrs_a)
            await _say(r.json()["total"] == 1, "3c. ?specialization=Cardiology -> 1")

            r = await c.get("/api/v1/doctors?specialization=Dermatology", headers=hdrs_a)
            await _say(r.json()["total"] == 0, "3d. ?specialization=Dermatology -> 0")

            # ============================================================
            # 4. GET one
            # ============================================================
            r = await c.get(f"/api/v1/doctors/{doctor_a_id}", headers=hdrs_a)
            await _say(r.status_code == 200, f"4a. GET one -> {r.status_code}")
            body = r.json()
            await _say(
                body["email"] == doc_user["email"]
                and body["last_name"] == "Smoke"
                and body["schedules"] == []
                and body["active_leaves"] == [],
                "4b. nested user fields present, schedules/leaves empty",
            )

            # ============================================================
            # 5. PATCH doctor
            # ============================================================
            r = await c.patch(
                f"/api/v1/doctors/{doctor_a_id}",
                json={"specialization": "Neurology", "consultation_fee": 750},
                headers=hdrs_a,
            )
            await _say(r.status_code == 200, f"5a. PATCH -> {r.status_code} {r.text[:160]}")
            body = r.json()
            await _say(
                body["specialization"] == "Neurology"
                and float(body["consultation_fee"]) == 750.0,
                f"5b. fields updated (spec={body['specialization']}, fee={body['consultation_fee']})",
            )

            # ============================================================
            # 6. Schedule CRUD — add Mon-Fri (day_of_week 1..5)
            # ============================================================
            schedule_ids = []
            for dow in (1, 2, 3, 4, 5):
                r = await c.post(
                    f"/api/v1/doctors/{doctor_a_id}/schedules",
                    json={
                        "day_of_week": dow,
                        "start_time": "09:00:00",
                        "end_time": "17:00:00",
                        "slot_duration_minutes": 15,
                    },
                    headers=hdrs_a,
                )
                assert r.status_code == 201, f"add schedule dow={dow}: {r.text[:160]}"
                schedule_ids.append(r.json()["id"])
            await _say(len(schedule_ids) == 5, "6a. added 5 schedules (Mon-Fri)")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}/schedules", headers=hdrs_a)
            await _say(
                r.status_code == 200 and len(r.json()) == 5,
                f"6b. list schedules -> {len(r.json())}",
            )

            r = await c.patch(
                f"/api/v1/doctors/{doctor_a_id}/schedules/{schedule_ids[0]}",
                json={"slot_duration_minutes": 30},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["slot_duration_minutes"] == 30,
                f"6c. update one schedule -> slot={r.json().get('slot_duration_minutes')}",
            )

            r = await c.delete(
                f"/api/v1/doctors/{doctor_a_id}/schedules/{schedule_ids[4]}",
                headers=hdrs_a,
            )
            await _say(r.status_code == 204, f"6d. delete one schedule -> {r.status_code}")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}/schedules", headers=hdrs_a)
            await _say(len(r.json()) == 4, f"6e. 4 schedules remain -> {len(r.json())}")
            a_schedule_id = schedule_ids[0]

            # ============================================================
            # 7. Leave CRUD — request, approve, filter
            # ============================================================
            l_start = (date.today() + timedelta(days=10)).isoformat()
            l_end = (date.today() + timedelta(days=12)).isoformat()
            r = await c.post(
                f"/api/v1/doctors/{doctor_a_id}/leaves",
                json={"start_date": l_start, "end_date": l_end, "reason": "Conference"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 201, f"7a. request leave -> {r.status_code} {r.text[:160]}")
            leave = r.json()
            await _say(
                leave["status"] == "pending" and leave["approved_by"] is None,
                "7b. new leave is pending, approved_by null",
            )
            a_leave_id = leave["id"]

            r = await c.patch(
                f"/api/v1/doctors/{doctor_a_id}/leaves/{a_leave_id}",
                json={"status": "approved"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 200, f"7c. PATCH leave->approved -> {r.status_code}")
            body = r.json()
            await _say(
                body["status"] == "approved"
                and body["approved_by"] is not None
                and body["approved_by_membership_id"] is not None,
                f"7d. approval audit populated (approved_by={body['approved_by']})",
            )

            # Date edit on approved leave must NOT clear audit (plan §6/§11g)
            r = await c.patch(
                f"/api/v1/doctors/{doctor_a_id}/leaves/{a_leave_id}",
                json={"reason": "Updated reason"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["approved_by"] is not None,
                "7e. editing reason on approved leave keeps approved_by",
            )

            r = await c.get(
                f"/api/v1/doctors/{doctor_a_id}/leaves?status=approved", headers=hdrs_a
            )
            await _say(len(r.json()) == 1, f"7f. filter status=approved -> {len(r.json())}")
            r = await c.get(
                f"/api/v1/doctors/{doctor_a_id}/leaves?status=pending", headers=hdrs_a
            )
            await _say(len(r.json()) == 0, f"7g. filter status=pending -> {len(r.json())}")

            # active_leaves on the doctor detail now shows the approved future leave
            r = await c.get(f"/api/v1/doctors/{doctor_a_id}", headers=hdrs_a)
            await _say(
                len(r.json()["active_leaves"]) == 1,
                f"7h. doctor.active_leaves shows approved future leave -> {len(r.json()['active_leaves'])}",
            )

            # ============================================================
            # 8. Override CRUD — full-day block + half-day + UNIQUE conflict
            # ============================================================
            o_date_block = (date.today() + timedelta(days=5)).isoformat()
            o_date_half = (date.today() + timedelta(days=6)).isoformat()

            r = await c.post(
                f"/api/v1/doctors/{doctor_a_id}/overrides",
                json={"override_date": o_date_block, "is_available": False,
                      "reason": "Public holiday"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 201, f"8a. full-day block override -> {r.status_code} {r.text[:160]}")
            a_override_id = r.json()["id"]

            r = await c.post(
                f"/api/v1/doctors/{doctor_a_id}/overrides",
                json={"override_date": o_date_half, "is_available": True,
                      "start_time": "09:00:00", "end_time": "12:00:00"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 201, f"8b. half-day override -> {r.status_code} {r.text[:160]}")

            r = await c.post(
                f"/api/v1/doctors/{doctor_a_id}/overrides",
                json={"override_date": o_date_block, "is_available": False},
                headers=hdrs_a,
            )
            await _say(r.status_code == 409, f"8c. duplicate override same date -> {r.status_code}")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}/overrides", headers=hdrs_a)
            await _say(len(r.json()) == 2, f"8d. list overrides -> {len(r.json())}")

            # ============================================================
            # 9. Cross-tenant — B admin must not touch A's doctor (404)
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")
            await _say(True, f"9a. hospital B bootstrapped ({hospital_b})")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}", headers=hdrs_b)
            await _say(r.status_code == 404, f"9b. B GET A's doctor -> {r.status_code}")

            r = await c.patch(
                f"/api/v1/doctors/{doctor_a_id}",
                json={"specialization": "Hijack"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"9c. B PATCH A's doctor -> {r.status_code}")

            r = await c.delete(f"/api/v1/doctors/{doctor_a_id}", headers=hdrs_b)
            await _say(r.status_code == 404, f"9d. B DELETE A's doctor -> {r.status_code}")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}/schedules", headers=hdrs_b)
            await _say(r.status_code == 404, f"9e. B LIST A's schedules -> {r.status_code}")

            r = await c.patch(
                f"/api/v1/doctors/{doctor_a_id}/schedules/{a_schedule_id}",
                json={"slot_duration_minutes": 60},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"9f. B PATCH A's schedule -> {r.status_code}")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}/leaves", headers=hdrs_b)
            await _say(r.status_code == 404, f"9g. B LIST A's leaves -> {r.status_code}")

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}/overrides", headers=hdrs_b)
            await _say(r.status_code == 404, f"9h. B LIST A's overrides -> {r.status_code}")

            r = await c.get("/api/v1/doctors", headers=hdrs_b)
            await _say(r.json()["total"] == 0, "9i. B sees zero doctors in its own list")

            # ============================================================
            # 10. Soft-delete doctor (is_active=false)
            # ============================================================
            r = await c.delete(f"/api/v1/doctors/{doctor_a_id}", headers=hdrs_a)
            await _say(r.status_code == 204, f"10a. deactivate doctor -> {r.status_code}")

            r = await c.get("/api/v1/doctors", headers=hdrs_a)
            await _say(r.json()["total"] == 0, "10b. default list excludes inactive doctor")

            r = await c.get("/api/v1/doctors?include_inactive=true", headers=hdrs_a)
            await _say(
                r.json()["total"] == 1
                and r.json()["items"][0]["is_active"] is False,
                "10c. ?include_inactive=true reveals the inactive doctor",
            )

            r = await c.get(f"/api/v1/doctors/{doctor_a_id}", headers=hdrs_a)
            await _say(
                r.status_code == 200 and r.json()["is_active"] is False,
                f"10d. GET still returns inactive doctor (no deleted_at) -> {r.status_code}",
            )

            # ============================================================
            # 11. Pagination — 25 doctors in B
            # ============================================================
            doctor_role_b = await _role_id(c, hdrs_b, "doctor")
            b_doctor_ids = []
            for i in range(25):
                u = await _invite_user(c, hdrs_b, doctor_role_b, f"bulk{i:02d}")
                r = await c.post(
                    "/api/v1/doctors",
                    json={"user_id": u["user_id"], "specialization": "General"},
                    headers=hdrs_b,
                )
                assert r.status_code == 201, f"bulk doctor {i}: {r.status_code} {r.text[:160]}"
                b_doctor_ids.append(r.json()["id"])

            r = await c.get("/api/v1/doctors?page=2&size=10", headers=hdrs_b)
            body = r.json()
            await _say(
                body["total"] == 25 and body["pages"] == 3
                and body["page"] == 2 and len(body["items"]) == 10,
                f"11. page=2 size=10 -> total=25 pages=3 items=10 "
                f"(got {body['total']}/{body['pages']}/{len(body['items'])})",
            )

            # ============================================================
            # 12. Negative validations
            # ============================================================
            b_doctor_id = b_doctor_ids[0]

            r = await c.post(
                f"/api/v1/doctors/{b_doctor_id}/schedules",
                json={"day_of_week": 9, "start_time": "09:00:00", "end_time": "17:00:00"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 422, f"12a. day_of_week=9 -> {r.status_code}")

            r = await c.post(
                f"/api/v1/doctors/{b_doctor_id}/schedules",
                json={"day_of_week": 1, "start_time": "17:00:00", "end_time": "09:00:00"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 422, f"12b. start_time>=end_time -> {r.status_code}")

            r = await c.post(
                f"/api/v1/doctors/{b_doctor_id}/leaves",
                json={"start_date": "2026-06-10", "end_date": "2026-06-01"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 422, f"12c. leave start_date>end_date -> {r.status_code}")

            nurse_role_b = await _role_id(c, hdrs_b, "nurse")
            nurse_user = await _invite_user(c, hdrs_b, nurse_role_b, "nurse")
            r = await c.post(
                "/api/v1/doctors",
                json={"user_id": nurse_user["user_id"], "specialization": "X"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 400, f"12d. non-doctor user_id -> {r.status_code} {r.text[:120]}")

        # ============================================================
        # 13. Demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "13. test user demoted from super_admin")

        print("\n========== PHASE 6 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 6 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

"""
Phase 10 end-to-end smoke test — Lab Tests + Lab Orders + Lab Results.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Test cases (printed [PASS] / [FAIL]) — per the approved Phase 10 plan:
   1.  Bootstrap hospital A + admin + doctor + patient + an ACTIVE
       visit; create a "CBC" lab-test catalogue entry.
   2.  Order "CBC" on the visit → 201, status 'ordered', created_by
       populated, has_result false, test_name denormalized.
   3.  GET the order → result is null, test catalogue entry nested.
   4.  PATCH ordered→collected (sample_collected_at stamped) →
       collected→in_progress.
   5.  POST the result (Hemoglobin 13.5) → 201, uploaded_by populated.
   6.  POST a second result → 409 (one-to-one UNIQUE constraint).
   7a. result_ready guard: a fresh in_progress order with NO result
       cannot move to result_ready → 400 with a clear message.
   7b. The main order (result entered) moves in_progress→result_ready
       → 200, result_ready_at stamped.
   8.  PATCH the result (correct a typo) → value updated, uploaded_by
       UNCHANGED (original lab tech preserved).
   9.  PATCH order result_ready→reviewed → result row's reviewed_by
       AND reviewed_at both populated.
   10. Invalid transitions: in_progress→reviewed → 400; mutating a
       terminal 'reviewed' order → 400; deleting it → 400.
   11. Cross-tenant: hospital B cannot read A's lab order or result
       → 404.
   12. List status filter: ?status=reviewed returns only the reviewed
       order; ?status=in_progress returns the in_progress one.
   13. Delete / cancel rules: DELETE a fresh 'ordered' order → 204;
       DELETE an 'in_progress' order → 400; PATCH-cancel a fresh
       'ordered' order → 200; PATCH-cancel an 'in_progress' order → 400.
   14. Order a lab on a 'closed' visit → 400 (visit must be
       active or completed).
   (cleanup) Demote the test user back to non-super.
"""

import asyncio
import sys
import uuid

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.database import AsyncSessionLocal  # noqa: F401 — ensures models register
from app.utils.security import hash_password


DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"
SEED_HOSPITAL_SLUG = "smoke10-platform"


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
            "VALUES ('Smoke10 Platform', $1, 'UTC') RETURNING id",
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
    slug = f"smoke10-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase10 {label.title()}",
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


async def _make_patient(c: httpx.AsyncClient, hdrs: dict) -> str:
    r = await c.post(
        "/api/v1/patients",
        json={"first_name": "Patient", "last_name": "Ten"},
        headers=hdrs,
    )
    assert r.status_code == 201, f"create patient: {r.text[:200]}"
    return r.json()["id"]


async def _make_visit(
    c: httpx.AsyncClient,
    hdrs: dict,
    patient_id: str,
    doctor_id: str,
    target_status: str = "active",
) -> str:
    """Create a visit (opens 'waiting') and advance it along the visit
    state machine to target_status. Returns the visit id."""
    r = await c.post(
        "/api/v1/visits",
        json={
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "chief_complaint": "Fever and fatigue",
        },
        headers=hdrs,
    )
    assert r.status_code == 201, f"create visit: {r.text[:200]}"
    visit_id = r.json()["id"]

    # waiting → active → completed → closed
    path = ["active", "completed", "closed"]
    for step in path:
        r = await c.patch(
            f"/api/v1/visits/{visit_id}",
            json={"status": step},
            headers=hdrs,
        )
        assert r.status_code == 200, f"advance visit→{step}: {r.text[:200]}"
        if step == target_status:
            break
    return visit_id


async def _make_lab_test(c: httpx.AsyncClient, hdrs: dict, name: str) -> str:
    r = await c.post(
        "/api/v1/lab-tests",
        json={
            "name": name,
            "category": "Hematology",
            "sample_type": "Blood",
            "unit": "g/dL",
        },
        headers=hdrs,
    )
    assert r.status_code == 201, f"create lab test {name}: {r.text[:200]}"
    return r.json()["id"]


async def _order_lab(
    c: httpx.AsyncClient, hdrs: dict, visit_id: str, test_id: str
) -> str:
    r = await c.post(
        f"/api/v1/visits/{visit_id}/lab-orders",
        json={"test_id": test_id},
        headers=hdrs,
    )
    assert r.status_code == 201, f"order lab: {r.status_code} {r.text[:200]}"
    return r.json()["id"]


async def _patch_status(
    c: httpx.AsyncClient, hdrs: dict, order_id: str, new_status: str
):
    return await c.patch(
        f"/api/v1/lab-orders/{order_id}",
        json={"status": new_status},
        headers=hdrs,
    )


async def _advance_to_in_progress(
    c: httpx.AsyncClient, hdrs: dict, order_id: str
) -> None:
    """Move an 'ordered' lab order through collected → in_progress."""
    for step in ("collected", "in_progress"):
        r = await _patch_status(c, hdrs, order_id, step)
        assert r.status_code == 200, f"advance order→{step}: {r.text[:200]}"


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
            # 1. Bootstrap hospital A + doctor + patient + active visit
            # ============================================================
            hospital_a, hdrs_a = await _bootstrap_hospital(c, super_hdrs, "a")
            doctor_a = await _make_doctor(c, hdrs_a, "drlab")
            patient_a = await _make_patient(c, hdrs_a)
            visit_a = await _make_visit(c, hdrs_a, patient_a, doctor_a, "active")
            test_cbc = await _make_lab_test(c, hdrs_a, "CBC")
            await _say(
                True,
                "1. hospital A + doctor + patient + active visit + CBC test ready",
            )

            # ============================================================
            # 2. Order a lab test on the visit
            # ============================================================
            r = await c.post(
                f"/api/v1/visits/{visit_a}/lab-orders",
                json={"test_id": test_cbc},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["status"] == "ordered"
                and body["created_by"] is not None
                and body["has_result"] is False
                and body["test_name"] == "CBC"
                and body["patient_id"] == patient_a
                and body["doctor_id"] == doctor_a,
                f"2. order CBC → {r.status_code}, status={body.get('status')}, "
                f"created_by set, has_result={body.get('has_result')}",
            )
            order_main = body["id"]

            # ============================================================
            # 3. GET the order — result null, test nested
            # ============================================================
            r = await c.get(f"/api/v1/lab-orders/{order_main}", headers=hdrs_a)
            body = r.json()
            await _say(
                r.status_code == 200
                and body["result"] is None
                and body["test"]["name"] == "CBC"
                and body["test"]["id"] == test_cbc,
                f"3. GET order → result={body.get('result')}, "
                f"test.name={body.get('test', {}).get('name')}",
            )

            # ============================================================
            # 4. Transition ordered → collected → in_progress
            # ============================================================
            r = await _patch_status(c, hdrs_a, order_main, "collected")
            body = r.json()
            collected_ok = (
                r.status_code == 200
                and body["status"] == "collected"
                and body["sample_collected_at"] is not None
            )
            r = await _patch_status(c, hdrs_a, order_main, "in_progress")
            in_progress_ok = (
                r.status_code == 200 and r.json()["status"] == "in_progress"
            )
            await _say(
                collected_ok and in_progress_ok,
                "4. ordered→collected (sample_collected_at stamped) "
                "→in_progress",
            )

            # ============================================================
            # 5. Record the result
            # ============================================================
            r = await c.post(
                f"/api/v1/lab-orders/{order_main}/result",
                json={
                    "result_value": "13.5",
                    "unit": "g/dL",
                    "reference_range": "13.0-17.0",
                    "is_abnormal": False,
                    "notes": "Hemoglobin within range",
                },
                headers=hdrs_a,
            )
            body = r.json()
            original_uploaded_by = body.get("uploaded_by")
            await _say(
                r.status_code == 201
                and body["result_value"] == "13.5"
                and original_uploaded_by is not None,
                f"5. POST result → {r.status_code}, value="
                f"{body.get('result_value')}, uploaded_by set",
            )

            # ============================================================
            # 6. Second result → 409 (one-to-one constraint)
            # ============================================================
            r = await c.post(
                f"/api/v1/lab-orders/{order_main}/result",
                json={"result_value": "99"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 409,
                f"6. POST a second result → {r.status_code} (one-to-one)",
            )

            # ============================================================
            # 7a. result_ready BEFORE a result exists → 400
            # ============================================================
            order_noresult = await _order_lab(c, hdrs_a, visit_a, test_cbc)
            await _advance_to_in_progress(c, hdrs_a, order_noresult)
            r = await _patch_status(c, hdrs_a, order_noresult, "result_ready")
            detail = r.json().get("detail", {})
            await _say(
                r.status_code == 400
                and "no result has been entered yet" in detail.get("message", ""),
                f"7a. result_ready with no result → {r.status_code}, "
                f"message={detail.get('message')!r}",
            )

            # ============================================================
            # 7b. Main order in_progress → result_ready (result exists)
            # ============================================================
            r = await _patch_status(c, hdrs_a, order_main, "result_ready")
            body = r.json()
            await _say(
                r.status_code == 200
                and body["status"] == "result_ready"
                and body["result_ready_at"] is not None,
                f"7b. in_progress→result_ready → status={body.get('status')}, "
                f"result_ready_at stamped",
            )

            # ============================================================
            # 8. Correct the result — uploaded_by unchanged
            # ============================================================
            r = await c.patch(
                f"/api/v1/lab-orders/{order_main}/result",
                json={"result_value": "13.6"},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 200
                and body["result_value"] == "13.6"
                and body["uploaded_by"] == original_uploaded_by,
                f"8. PATCH result (typo fix) → value={body.get('result_value')}, "
                f"uploaded_by unchanged ({body.get('uploaded_by') == original_uploaded_by})",
            )

            # ============================================================
            # 9. Doctor review — reviewed_by + reviewed_at stamped
            # ============================================================
            r = await _patch_status(c, hdrs_a, order_main, "reviewed")
            await _say(
                r.status_code == 200 and r.json()["status"] == "reviewed",
                f"9a. result_ready→reviewed → {r.status_code}",
            )
            r = await c.get(
                f"/api/v1/lab-orders/{order_main}/result", headers=hdrs_a
            )
            body = r.json()
            await _say(
                r.status_code == 200
                and body["reviewed_by"] is not None
                and body["reviewed_at"] is not None,
                f"9b. result reviewed_by AND reviewed_at both populated "
                f"(reviewed_by={body.get('reviewed_by') is not None}, "
                f"reviewed_at={body.get('reviewed_at') is not None})",
            )

            # ============================================================
            # 10. Invalid transitions
            # ============================================================
            r = await _patch_status(c, hdrs_a, order_noresult, "reviewed")
            await _say(
                r.status_code == 400,
                f"10a. in_progress→reviewed (skipping result_ready) → "
                f"{r.status_code}",
            )
            r = await _patch_status(c, hdrs_a, order_main, "collected")
            await _say(
                r.status_code == 400,
                f"10b. mutate a terminal 'reviewed' order → {r.status_code}",
            )
            r = await c.delete(
                f"/api/v1/lab-orders/{order_main}", headers=hdrs_a
            )
            await _say(
                r.status_code == 400,
                f"10c. DELETE a 'reviewed' order → {r.status_code}",
            )

            # ============================================================
            # 11. Cross-tenant isolation
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")
            r = await c.get(
                f"/api/v1/lab-orders/{order_main}", headers=hdrs_b
            )
            cross_order = r.status_code == 404
            r = await c.get(
                f"/api/v1/lab-orders/{order_main}/result", headers=hdrs_b
            )
            cross_result = r.status_code == 404
            await _say(
                cross_order and cross_result,
                "11. hospital B cannot read A's lab order or result → 404",
            )

            # ============================================================
            # 12. List status filter
            # ============================================================
            r = await c.get(
                "/api/v1/lab-orders?status=reviewed", headers=hdrs_a
            )
            reviewed_ids = {o["id"] for o in r.json()["items"]}
            reviewed_ok = (
                r.status_code == 200
                and order_main in reviewed_ids
                and order_noresult not in reviewed_ids
                and all(o["status"] == "reviewed" for o in r.json()["items"])
            )
            r = await c.get(
                "/api/v1/lab-orders?status=in_progress", headers=hdrs_a
            )
            in_prog_ids = {o["id"] for o in r.json()["items"]}
            in_prog_ok = (
                r.status_code == 200
                and order_noresult in in_prog_ids
                and order_main not in in_prog_ids
            )
            await _say(
                reviewed_ok and in_prog_ok,
                "12. ?status=reviewed → only reviewed orders; "
                "?status=in_progress → only in_progress orders",
            )

            # ============================================================
            # 13. Delete / cancel rules
            # ============================================================
            order_del = await _order_lab(c, hdrs_a, visit_a, test_cbc)
            r = await c.delete(
                f"/api/v1/lab-orders/{order_del}", headers=hdrs_a
            )
            await _say(
                r.status_code == 204,
                f"13a. DELETE a fresh 'ordered' order → {r.status_code}",
            )

            r = await c.delete(
                f"/api/v1/lab-orders/{order_noresult}", headers=hdrs_a
            )
            await _say(
                r.status_code == 400,
                f"13b. DELETE an 'in_progress' order → {r.status_code}",
            )

            order_cancel = await _order_lab(c, hdrs_a, visit_a, test_cbc)
            r = await _patch_status(c, hdrs_a, order_cancel, "cancelled")
            await _say(
                r.status_code == 200 and r.json()["status"] == "cancelled",
                f"13c. PATCH-cancel a fresh 'ordered' order → {r.status_code}",
            )

            r = await _patch_status(c, hdrs_a, order_noresult, "cancelled")
            await _say(
                r.status_code == 400,
                f"13d. PATCH-cancel an 'in_progress' order → {r.status_code}",
            )

            # ============================================================
            # 14. Order a lab on a 'closed' visit → 400
            # ============================================================
            visit_closed = await _make_visit(
                c, hdrs_a, patient_a, doctor_a, "closed"
            )
            r = await c.post(
                f"/api/v1/visits/{visit_closed}/lab-orders",
                json={"test_id": test_cbc},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"14. order a lab on a 'closed' visit → {r.status_code}",
            )

        # ============================================================
        # Cleanup — demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "cleanup: test user demoted from super_admin")

        print("\n========== PHASE 10 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 10 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

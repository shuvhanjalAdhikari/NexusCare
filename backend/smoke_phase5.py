"""
Phase 5 end-to-end smoke test — Patient module.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin for the duration so we can
bootstrap fresh hospitals, then demoted at the end.

Test cases (all printed with [PASS] / [FAIL] prefix):
   1.  Bootstrap hospital A + admin via /admin/hospitals.
   2.  Create 3 patients in A; verify unique patient_numbers (P-* format).
   3.  GET one patient — allergies = [], full shape returned.
   4.  GET /patients — paged shape, total=3, default sort = recent (DESC).
   5.  Search: ?q=<first_name fragment>, ?q=P-, ?gender=, ?blood_group=.
   6.  PATCH a patient (phone + address). Verify patient_number unchanged.
   7.  Allergies: POST x2, GET (sorted), PATCH severity, DELETE one.
   8.  Soft-delete a patient — GET 404, list excludes it, total=2.
   9.  DOB future-date rejection — 422.
   10. include_inactive flag honoured.
   11. Bootstrap hospital B + admin (separate tenant).
   12. Cross-tenant: B admin hits A's patient → 404 on GET/PATCH/DELETE/POST.
   13. Pagination: 25 patients in B, ?page=1&size=10 → pages=3, total=25.
   14. Demote test user back to non-super.
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


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


async def _bootstrap_hospital(c: httpx.AsyncClient, super_hdrs: dict, label: str):
    """Creates a fresh hospital + admin and returns (hospital_id, admin headers)."""
    slug = f"smoke5-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase5 {label.title()}",
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


async def main() -> None:
    pg = await asyncpg.connect(DB_URL)
    try:
        # ---- promote test user to super_admin (and reset password / lockouts) ----
        new_hash = hash_password(TEST_USER_PASSWORD)
        await pg.execute(
            "UPDATE users SET system_role='super_admin', password_hash=$2, "
            "failed_login_attempts=0, locked_until=NULL WHERE email=$1",
            TEST_USER_EMAIL,
            new_hash,
        )
        await _say(True, "test user promoted to super_admin")

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
            # 2. Create 3 patients
            # ============================================================
            patients_a = []
            for fn, ln, gender, bg, phone in [
                ("Alice",   "Anderson", "female", "O+",  "+9779800000001"),
                ("Bob",     "Brown",    "male",   "A-",  "+9779800000002"),
                ("Charlie", "Cohen",    "other",  None,  None),
            ]:
                payload = {"first_name": fn, "last_name": ln, "gender": gender}
                if bg:
                    payload["blood_group"] = bg
                if phone:
                    payload["phone"] = phone
                r = await c.post("/api/v1/patients", json=payload, headers=hdrs_a)
                assert r.status_code == 201, f"create {fn}: {r.status_code} {r.text[:200]}"
                patients_a.append(r.json())

            numbers = [p["patient_number"] for p in patients_a]
            await _say(
                all(n.startswith("P-") and len(n) == 8 for n in numbers),
                f"2a. patient_numbers shape P-XXXXXX: {numbers}",
            )
            await _say(len(set(numbers)) == 3, "2b. all 3 patient_numbers unique")

            p1, p2, p3 = patients_a  # creation order

            # ============================================================
            # 3. GET one patient with allergies
            # ============================================================
            r = await c.get(f"/api/v1/patients/{p2['id']}", headers=hdrs_a)
            await _say(r.status_code == 200, f"3a. GET one -> {r.status_code}")
            body = r.json()
            await _say(
                body["first_name"] == "Bob" and body["allergies"] == [],
                "3b. response shape includes empty allergies",
            )

            # ============================================================
            # 4. List: paged shape + default sort = recent (DESC)
            # ============================================================
            r = await c.get("/api/v1/patients", headers=hdrs_a)
            await _say(r.status_code == 200, f"4a. LIST -> {r.status_code}")
            body = r.json()
            await _say(
                body["total"] == 3
                and body["page"] == 1
                and body["pages"] == 1
                and len(body["items"]) == 3,
                f"4b. paged shape total=3 pages=1: {body['total']}/{body['pages']}",
            )
            await _say(
                body["items"][0]["id"] == p3["id"]
                and body["items"][-1]["id"] == p1["id"],
                "4c. default sort=recent -> newest first",
            )

            # Verify sort=name flips order
            r = await c.get("/api/v1/patients?sort=name", headers=hdrs_a)
            names = [it["first_name"] for it in r.json()["items"]]
            await _say(names == ["Alice", "Bob", "Charlie"], f"4d. sort=name -> {names}")

            # ============================================================
            # 5. Search filters
            # ============================================================
            r = await c.get("/api/v1/patients?q=Bob", headers=hdrs_a)
            await _say(
                r.status_code == 200
                and r.json()["total"] == 1
                and r.json()["items"][0]["id"] == p2["id"],
                "5a. q=Bob matches first_name",
            )

            r = await c.get("/api/v1/patients?q=P-", headers=hdrs_a)
            await _say(r.json()["total"] == 3, "5b. q=P- matches patient_number for all 3")

            r = await c.get("/api/v1/patients?gender=female", headers=hdrs_a)
            await _say(r.json()["total"] == 1, "5c. gender=female -> 1 match")

            r = await c.get("/api/v1/patients?blood_group=O%2B", headers=hdrs_a)
            await _say(r.json()["total"] == 1, "5d. blood_group=O+ -> 1 match")

            r = await c.get("/api/v1/patients?q=Anderson", headers=hdrs_a)
            await _say(r.json()["total"] == 1, "5e. q=Anderson matches last_name")

            # ============================================================
            # 6. PATCH a patient — verify update + immutable patient_number
            # ============================================================
            r = await c.patch(
                f"/api/v1/patients/{p1['id']}",
                json={"phone": "+9779811111111", "address": "Ward 5, Kathmandu"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 200, f"6a. PATCH -> {r.status_code}: {r.text[:200]}")
            body = r.json()
            await _say(
                body["phone"] == "+9779811111111"
                and body["address"] == "Ward 5, Kathmandu"
                and body["patient_number"] == p1["patient_number"],
                "6b. fields updated, patient_number unchanged",
            )

            # PatientUpdate has no patient_number field — sending it is silently
            # ignored by Pydantic v2 default behaviour (extra fields ignored).
            r = await c.patch(
                f"/api/v1/patients/{p1['id']}",
                json={"patient_number": "P-HACKED"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 200, "6c. unknown 'patient_number' field ignored by PatientUpdate")
            r = await c.get(f"/api/v1/patients/{p1['id']}", headers=hdrs_a)
            await _say(
                r.json()["patient_number"] == p1["patient_number"],
                "6d. patient_number still original after the attempt",
            )

            # ============================================================
            # 7. Allergies CRUD
            # ============================================================
            r = await c.post(
                f"/api/v1/patients/{p2['id']}/allergies",
                json={"allergen": "Penicillin", "severity": "severe", "reaction": "rash"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 201, f"7a. add allergy 1 -> {r.status_code}")
            allergy_pen = r.json()

            r = await c.post(
                f"/api/v1/patients/{p2['id']}/allergies",
                json={"allergen": "Peanut", "severity": "moderate"},
                headers=hdrs_a,
            )
            await _say(r.status_code == 201, f"7b. add allergy 2 -> {r.status_code}")
            allergy_pea = r.json()

            r = await c.get(f"/api/v1/patients/{p2['id']}/allergies", headers=hdrs_a)
            await _say(
                r.status_code == 200 and len(r.json()) == 2,
                f"7c. list allergies -> {len(r.json())}",
            )

            # Nested response on patient GET should include both allergies
            r = await c.get(f"/api/v1/patients/{p2['id']}", headers=hdrs_a)
            await _say(
                len(r.json()["allergies"]) == 2,
                "7d. patient GET returns nested allergies (selectinload)",
            )

            # PATCH severity
            r = await c.patch(
                f"/api/v1/patients/{p2['id']}/allergies/{allergy_pen['id']}",
                json={"severity": "life_threatening"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["severity"] == "life_threatening",
                f"7e. PATCH severity -> {r.json().get('severity')}",
            )

            # DELETE one
            r = await c.delete(
                f"/api/v1/patients/{p2['id']}/allergies/{allergy_pea['id']}",
                headers=hdrs_a,
            )
            await _say(r.status_code == 204, f"7f. DELETE allergy -> {r.status_code}")

            r = await c.get(f"/api/v1/patients/{p2['id']}/allergies", headers=hdrs_a)
            await _say(len(r.json()) == 1, "7g. 1 allergy remains after delete")

            # ============================================================
            # 8. Soft-delete a patient
            # ============================================================
            r = await c.delete(f"/api/v1/patients/{p3['id']}", headers=hdrs_a)
            await _say(r.status_code == 204, f"8a. soft-delete -> {r.status_code}")

            r = await c.get(f"/api/v1/patients/{p3['id']}", headers=hdrs_a)
            await _say(r.status_code == 404, f"8b. GET deleted patient -> {r.status_code}")

            r = await c.get("/api/v1/patients", headers=hdrs_a)
            ids_in_list = [it["id"] for it in r.json()["items"]]
            await _say(
                r.json()["total"] == 2 and p3["id"] not in ids_in_list,
                f"8c. list excludes deleted patient (total={r.json()['total']})",
            )

            # Even include_inactive=true must not surface deleted rows
            r = await c.get("/api/v1/patients?include_inactive=true", headers=hdrs_a)
            ids_in_list = [it["id"] for it in r.json()["items"]]
            await _say(p3["id"] not in ids_in_list, "8d. include_inactive still hides deleted_at != null")

            # ============================================================
            # 9. DOB future-date rejection (422)
            # ============================================================
            future = (date.today() + timedelta(days=7)).isoformat()
            r = await c.post(
                "/api/v1/patients",
                json={"first_name": "Future", "last_name": "Born", "dob": future},
                headers=hdrs_a,
            )
            await _say(r.status_code == 422, f"9. DOB in future -> {r.status_code}")

            # ============================================================
            # 10. include_inactive flag
            # ============================================================
            # Suspend p2 (is_active=false) → default list hides it; include_inactive shows it.
            r = await c.patch(
                f"/api/v1/patients/{p2['id']}",
                json={"is_active": False},
                headers=hdrs_a,
            )
            assert r.status_code == 200, r.text[:200]

            r = await c.get("/api/v1/patients", headers=hdrs_a)
            await _say(r.json()["total"] == 1, "10a. default list hides is_active=false")

            r = await c.get("/api/v1/patients?include_inactive=true", headers=hdrs_a)
            await _say(r.json()["total"] == 2, "10b. include_inactive=true reveals both")

            # ============================================================
            # 11. Bootstrap hospital B
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")
            await _say(True, f"11. hospital B bootstrapped ({hospital_b})")

            # ============================================================
            # 12. Cross-tenant — every operation on A's patient from B → 404
            # ============================================================
            r = await c.get(f"/api/v1/patients/{p1['id']}", headers=hdrs_b)
            await _say(r.status_code == 404, f"12a. B GET A's patient -> {r.status_code}")

            r = await c.patch(
                f"/api/v1/patients/{p1['id']}",
                json={"first_name": "Hijack"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"12b. B PATCH A's patient -> {r.status_code}")

            r = await c.delete(f"/api/v1/patients/{p1['id']}", headers=hdrs_b)
            await _say(r.status_code == 404, f"12c. B DELETE A's patient -> {r.status_code}")

            r = await c.post(
                f"/api/v1/patients/{p1['id']}/allergies",
                json={"allergen": "Aspirin"},
                headers=hdrs_b,
            )
            await _say(r.status_code == 404, f"12d. B POST allergy on A's patient -> {r.status_code}")

            r = await c.get(f"/api/v1/patients/{p1['id']}/allergies", headers=hdrs_b)
            await _say(r.status_code == 404, f"12e. B LIST allergies on A's patient -> {r.status_code}")

            # B's patient list must be empty (no cross-tenant leakage)
            r = await c.get("/api/v1/patients", headers=hdrs_b)
            await _say(r.json()["total"] == 0, "12f. B sees zero patients in its own list")

            # ============================================================
            # 13. Pagination: 25 patients in B, size=10 → pages=3
            # ============================================================
            for i in range(25):
                r = await c.post(
                    "/api/v1/patients",
                    json={"first_name": f"Bulk{i:02d}", "last_name": "Pager"},
                    headers=hdrs_b,
                )
                assert r.status_code == 201, f"bulk {i}: {r.status_code}"

            r = await c.get("/api/v1/patients?page=1&size=10", headers=hdrs_b)
            body = r.json()
            await _say(
                body["total"] == 25 and body["pages"] == 3 and len(body["items"]) == 10,
                f"13a. page=1 size=10 -> total=25 pages=3 items=10 (got {body['total']}/{body['pages']}/{len(body['items'])})",
            )

            r = await c.get("/api/v1/patients?page=3&size=10", headers=hdrs_b)
            body = r.json()
            await _say(
                len(body["items"]) == 5,
                f"13b. page=3 size=10 -> 5 items (got {len(body['items'])})",
            )

        # ============================================================
        # 14. Demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "14. test user demoted from super_admin")

        print("\n========== PHASE 5 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 5 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

"""
Phase 9 end-to-end smoke test — Drugs + Inventory + Prescriptions +
Dispensing.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Test cases (printed [PASS] / [FAIL]) — per the approved Phase 9 plan:
   1.  Bootstrap hospital A + admin + doctor + patient + a visit.
   2.  Drug CRUD: create, GET (total_active_stock = 0), PATCH, list
       with a `q` substring filter.
   3.  Add 2 batches to drug1; stock breakdown of a 3-batch drug —
       expired batch excluded from the total, near-expiry flagged.
   4.  Low-stock report — a drug with no batches shows up below
       threshold via GET /api/v1/inventory/low-stock.
   5.  Create a prescription (nested under the visit) → 201, status
       'draft', 2 items, derived progress fields all zero.
   6.  Create prescription with an unknown drug → 404; with an
       inactive drug → 400.
   7.  GET prescription detail; list prescriptions filtered by visit.
   8.  PATCH draft→dispensed → 400 (manual dispense forbidden);
       PATCH draft→issued → 200, issued_at stamped.
   9.  Dispense item1 (FIFO auto-select) → 201, earliest-expiry batch
       drawn down, prescription still 'issued'.
   10. Dispense item1 again with an explicit batch_id → item1 fully
       dispensed, prescription still 'issued' (item2 outstanding).
   11. Over-dispense item1 → 422; refinement #5: no dispense_logs row
       was written for the failed attempt.
   12. Insufficient stock for item2 (explicit short batch) → 422;
       refinement #5: still no dispense_logs row for item2.
   13. Cross-tenant: hospital B cannot read A's drug / prescription or
       dispense A's item → 404.
   14. Dispense item2 in full → prescription auto-flips to 'dispensed';
       GET detail shows every item fully dispensed.
   15. Dispense against the now-'dispensed' prescription → 400.
   16. Concurrent dispense of the last unit (refinement #2): two
       parallel requests → exactly one 201 + one 422, and exactly one
       dispense_logs row exists for that item.
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
SEED_HOSPITAL_SLUG = "smoke9-platform"


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


def _iso(d: date) -> str:
    """ISO date string for a batch expiry / purchase date field."""
    return d.isoformat()


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
            "VALUES ('Smoke9 Platform', $1, 'UTC') RETURNING id",
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
    slug = f"smoke9-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase9 {label.title()}",
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


async def _make_drug(
    c: httpx.AsyncClient, hdrs: dict, name: str, **extra
) -> str:
    """Create a catalogue drug; return its id."""
    payload = {"name": name}
    payload.update(extra)
    r = await c.post("/api/v1/drugs", json=payload, headers=hdrs)
    assert r.status_code == 201, f"create drug {name}: {r.status_code} {r.text[:200]}"
    return r.json()["id"]


async def _add_batch(
    c: httpx.AsyncClient,
    hdrs: dict,
    drug_id: str,
    batch_number: str,
    expiry: date,
    stock: int,
) -> str:
    """Receive a stock batch for a drug; return the batch id."""
    r = await c.post(
        f"/api/v1/drugs/{drug_id}/batches",
        json={
            "batch_number": batch_number,
            "expiry_date": _iso(expiry),
            "stock_quantity": stock,
        },
        headers=hdrs,
    )
    assert r.status_code == 201, f"add batch {batch_number}: {r.text[:200]}"
    return r.json()["id"]


async def _log_count(pg: asyncpg.Connection, item_id: str) -> int:
    """Count dispense_logs rows for one prescription item."""
    return await pg.fetchval(
        "SELECT count(*) FROM dispense_logs WHERE prescription_item_id = $1",
        uuid.UUID(item_id),
    )


async def main() -> None:
    pg = await asyncpg.connect(DB_URL)
    try:
        await _seed_super_admin(pg)
        await _say(True, "super_admin test user + seed workspace ready")

        today = date.today()
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
            # 1. Bootstrap hospital A + doctor + patient + visit
            # ============================================================
            hospital_a, hdrs_a = await _bootstrap_hospital(c, super_hdrs, "a")
            doctor_a = await _make_doctor(c, hdrs_a, "drhouse")

            r = await c.post(
                "/api/v1/patients",
                json={"first_name": "Patient", "last_name": "Nine"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create patient: {r.text[:200]}"
            patient_a = r.json()["id"]

            r = await c.post(
                "/api/v1/visits",
                json={
                    "patient_id": patient_a,
                    "doctor_id": doctor_a,
                    "chief_complaint": "Fever and body ache",
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create visit: {r.text[:200]}"
            visit_a = r.json()["id"]
            await _say(True, "1. hospital A + doctor + patient + visit ready")

            # ============================================================
            # 2. Drug CRUD
            # ============================================================
            drug1 = await _make_drug(
                c, hdrs_a, "Paracetamol 500", generic_name="paracetamol",
                form="tablet", unit_price="2.50",
            )
            r = await c.get(f"/api/v1/drugs/{drug1}", headers=hdrs_a)
            body = r.json()
            await _say(
                r.status_code == 200 and body["total_active_stock"] == 0,
                f"2a. GET drug → total_active_stock={body.get('total_active_stock')} "
                f"(expected 0)",
            )

            r = await c.patch(
                f"/api/v1/drugs/{drug1}",
                json={"name": "Paracetamol 500mg"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["name"] == "Paracetamol 500mg",
                f"2b. PATCH drug name → {r.status_code}",
            )

            r = await c.get("/api/v1/drugs?q=paracet", headers=hdrs_a)
            ids = {d["id"] for d in r.json()["items"]}
            await _say(
                r.status_code == 200 and drug1 in ids,
                f"2c. list drugs q='paracet' → total={r.json().get('total')}",
            )

            # ============================================================
            # 3. Batches + stock breakdown
            # ============================================================
            batch_a = await _add_batch(
                c, hdrs_a, drug1, "PARA-A", today + timedelta(days=60), 8
            )
            batch_b = await _add_batch(
                c, hdrs_a, drug1, "PARA-B", today + timedelta(days=120), 20
            )

            drug_stock = await _make_drug(c, hdrs_a, "StockTest Syrup", form="syrup")
            await _add_batch(
                c, hdrs_a, drug_stock, "ST-EXPIRED", today - timedelta(days=10), 100
            )
            await _add_batch(
                c, hdrs_a, drug_stock, "ST-NEAR", today + timedelta(days=15), 30
            )
            await _add_batch(
                c, hdrs_a, drug_stock, "ST-FAR", today + timedelta(days=200), 50
            )
            r = await c.get(f"/api/v1/drugs/{drug_stock}/stock", headers=hdrs_a)
            body = r.json()
            await _say(
                r.status_code == 200
                and body["total_active_stock"] == 80
                and body["near_expiry_count"] == 1
                and len(body["batches"]) == 3,
                f"3. stock breakdown → total={body.get('total_active_stock')} "
                f"(expected 80), near_expiry={body.get('near_expiry_count')} "
                f"(expected 1)",
            )

            # ============================================================
            # 4. Low-stock report
            # ============================================================
            drug_empty = await _make_drug(c, hdrs_a, "EmptyShelf Tablet", form="tablet")
            r = await c.get("/api/v1/inventory/low-stock?threshold=5", headers=hdrs_a)
            low_ids = {d["drug_id"] for d in r.json()}
            await _say(
                r.status_code == 200 and drug_empty in low_ids,
                f"4. low-stock report (threshold=5) includes the empty drug → "
                f"{len(r.json())} drug(s)",
            )

            # ============================================================
            # 5. Create a prescription nested under the visit
            # ============================================================
            drug2 = await _make_drug(
                c, hdrs_a, "Amoxicillin 250mg", generic_name="amoxicillin",
                form="capsule",
            )
            batch_c = await _add_batch(
                c, hdrs_a, drug2, "AMOX-C", today + timedelta(days=90), 5
            )
            batch_d = await _add_batch(
                c, hdrs_a, drug2, "AMOX-D", today + timedelta(days=90), 2
            )

            r = await c.post(
                f"/api/v1/visits/{visit_a}/prescriptions",
                json={
                    "notes": "Take after meals",
                    "items": [
                        {"drug_id": drug1, "quantity": 10, "dose": "1 tab",
                         "frequency": "TID"},
                        {"drug_id": drug2, "quantity": 5, "dose": "1 cap",
                         "frequency": "BID"},
                    ],
                },
                headers=hdrs_a,
            )
            body = r.json()
            zero_progress = all(
                it["dispensed_quantity"] == 0
                and it["remaining_quantity"] == it["quantity"]
                and it["is_fully_dispensed"] is False
                for it in body.get("items", [])
            )
            await _say(
                r.status_code == 201
                and body["status"] == "draft"
                and len(body["items"]) == 2
                and zero_progress,
                f"5. create prescription → {r.status_code}, status="
                f"{body.get('status')}, items={len(body.get('items', []))}, "
                f"progress fields zeroed",
            )
            prescription_a = body["id"]
            item_by_drug = {it["drug_id"]: it["id"] for it in body["items"]}
            item1 = item_by_drug[drug1]
            item2 = item_by_drug[drug2]

            # ============================================================
            # 6. Create prescription with bad drug references
            # ============================================================
            r = await c.post(
                f"/api/v1/visits/{visit_a}/prescriptions",
                json={"items": [{"drug_id": str(uuid.uuid4()), "quantity": 1}]},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 404,
                f"6a. prescription with unknown drug → {r.status_code}",
            )

            drug_dead = await _make_drug(c, hdrs_a, "Deprecated Drug")
            r = await c.delete(f"/api/v1/drugs/{drug_dead}", headers=hdrs_a)
            assert r.status_code == 204, f"deactivate drug: {r.status_code}"
            r = await c.post(
                f"/api/v1/visits/{visit_a}/prescriptions",
                json={"items": [{"drug_id": drug_dead, "quantity": 1}]},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"6b. prescription with inactive drug → {r.status_code}",
            )

            # ============================================================
            # 7. GET detail + list filtered by visit
            # ============================================================
            r = await c.get(
                f"/api/v1/prescriptions/{prescription_a}", headers=hdrs_a
            )
            await _say(
                r.status_code == 200 and len(r.json()["items"]) == 2,
                f"7a. GET prescription detail → {len(r.json().get('items', []))} items",
            )
            r = await c.get(
                f"/api/v1/prescriptions?visit_id={visit_a}", headers=hdrs_a
            )
            ids = {p["id"] for p in r.json()["items"]}
            await _say(
                r.status_code == 200 and prescription_a in ids,
                f"7b. list prescriptions by visit → total={r.json().get('total')}",
            )

            # ============================================================
            # 8. PATCH status: dispensed forbidden, issued allowed
            # ============================================================
            r = await c.patch(
                f"/api/v1/prescriptions/{prescription_a}",
                json={"status": "dispensed"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"8a. PATCH draft→dispensed (manual) → {r.status_code}",
            )
            r = await c.patch(
                f"/api/v1/prescriptions/{prescription_a}",
                json={"status": "issued"},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 200
                and body["status"] == "issued"
                and body["issued_at"] is not None,
                f"8b. PATCH draft→issued → status={body.get('status')}, "
                f"issued_at set",
            )

            # ============================================================
            # 9. Dispense item1 — FIFO auto-select
            # ============================================================
            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item1}/dispense",
                json={"quantity": 6},
                headers=hdrs_a,
            )
            body = r.json()
            drew_from_a = body.get("dispense_log", {}).get("batch_id") == batch_a
            await _say(
                r.status_code == 201
                and drew_from_a
                and body["batch_remaining_stock"] == 2
                and body["item_dispensed_quantity"] == 6
                and body["item_fully_dispensed"] is False
                and body["prescription_status"] == "issued",
                f"9. dispense item1 x6 (FIFO) → drew from earliest-expiry batch="
                f"{drew_from_a}, batch left={body.get('batch_remaining_stock')} "
                f"(expected 2)",
            )

            # ============================================================
            # 10. Dispense item1 again — explicit batch_id
            # ============================================================
            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item1}/dispense",
                json={"quantity": 4, "batch_id": batch_b},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["dispense_log"]["batch_id"] == batch_b
                and body["item_dispensed_quantity"] == 10
                and body["item_remaining_quantity"] == 0
                and body["item_fully_dispensed"] is True
                and body["prescription_status"] == "issued",
                f"10. dispense item1 x4 (explicit batch) → item fully dispensed, "
                f"prescription still '{body.get('prescription_status')}'",
            )

            # ============================================================
            # 11. Over-dispense item1 → 422, no log written
            # ============================================================
            before = await _log_count(pg, item1)
            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item1}/dispense",
                json={"quantity": 1},
                headers=hdrs_a,
            )
            after = await _log_count(pg, item1)
            await _say(
                r.status_code == 422 and before == after == 2,
                f"11. over-dispense item1 → {r.status_code}; dispense_logs "
                f"unchanged ({before}→{after}, refinement #5)",
            )

            # ============================================================
            # 12. Insufficient stock for item2 → 422, no log written
            # ============================================================
            before = await _log_count(pg, item2)
            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item2}/dispense",
                json={"quantity": 4, "batch_id": batch_d},
                headers=hdrs_a,
            )
            after = await _log_count(pg, item2)
            await _say(
                r.status_code == 422 and before == after == 0,
                f"12. insufficient stock for item2 → {r.status_code}; no "
                f"dispense_logs row ({before}→{after}, refinement #5)",
            )

            # ============================================================
            # 13. Cross-tenant isolation
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")

            r = await c.get(f"/api/v1/drugs/{drug1}", headers=hdrs_b)
            await _say(r.status_code == 404, f"13a. B GET A's drug → {r.status_code}")

            r = await c.get(
                f"/api/v1/prescriptions/{prescription_a}", headers=hdrs_b
            )
            await _say(
                r.status_code == 404,
                f"13b. B GET A's prescription → {r.status_code}",
            )

            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item2}/dispense",
                json={"quantity": 1},
                headers=hdrs_b,
            )
            await _say(
                r.status_code == 404,
                f"13c. B dispense A's prescription item → {r.status_code}",
            )

            # ============================================================
            # 14. Dispense item2 fully → prescription auto 'dispensed'
            # ============================================================
            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item2}/dispense",
                json={"quantity": 5, "batch_id": batch_c},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["item_fully_dispensed"] is True
                and body["prescription_status"] == "dispensed",
                f"14a. dispense item2 x5 → prescription auto-flipped to "
                f"'{body.get('prescription_status')}'",
            )
            r = await c.get(
                f"/api/v1/prescriptions/{prescription_a}", headers=hdrs_a
            )
            body = r.json()
            await _say(
                r.status_code == 200
                and body["status"] == "dispensed"
                and all(it["is_fully_dispensed"] for it in body["items"]),
                f"14b. GET detail → status='{body.get('status')}', every item "
                f"fully dispensed",
            )

            # ============================================================
            # 15. Dispense against a 'dispensed' prescription → 400
            # ============================================================
            r = await c.post(
                f"/api/v1/prescriptions/{prescription_a}/items/{item1}/dispense",
                json={"quantity": 1},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"15. dispense against dispensed prescription → {r.status_code}",
            )

            # ============================================================
            # 16. Concurrent dispense of the last unit (refinement #2)
            # ============================================================
            drug3 = await _make_drug(c, hdrs_a, "Ibuprofen 400mg", form="tablet")
            await _add_batch(
                c, hdrs_a, drug3, "IBU-E", today + timedelta(days=90), 1
            )
            r = await c.post(
                f"/api/v1/visits/{visit_a}/prescriptions",
                json={"items": [{"drug_id": drug3, "quantity": 1}]},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create rx3: {r.text[:200]}"
            rx3 = r.json()["id"]
            item3 = r.json()["items"][0]["id"]
            r = await c.patch(
                f"/api/v1/prescriptions/{rx3}",
                json={"status": "issued"},
                headers=hdrs_a,
            )
            assert r.status_code == 200, f"issue rx3: {r.text[:200]}"

            async def _dispense_one():
                return await c.post(
                    f"/api/v1/prescriptions/{rx3}/items/{item3}/dispense",
                    json={"quantity": 1},
                    headers=hdrs_a,
                )

            r1, r2 = await asyncio.gather(_dispense_one(), _dispense_one())
            statuses = sorted([r1.status_code, r2.status_code])
            log_rows = await _log_count(pg, item3)
            await _say(
                statuses == [201, 422] and log_rows == 1,
                f"16. concurrent dispense of last unit → statuses={statuses} "
                f"(expected [201, 422]); dispense_logs rows={log_rows} "
                f"(expected 1, refinement #2)",
            )

        # ============================================================
        # Cleanup — demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "cleanup: test user demoted from super_admin")

        print("\n========== PHASE 9 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 9 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

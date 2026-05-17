"""
Phase 11 end-to-end smoke test — Billing: Invoices + Payments.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Requires migration b1c2d3e4f5a6 (lab_tests.price) to be applied:
    cd backend && alembic upgrade head

Test cases (printed [PASS] / [FAIL]) — per the approved Phase 11 plan:
   1.  Bootstrap hospital A + admin + doctor (consultation_fee=500) +
       patient + active visit.
   2.  Prescription: drug @ 25 x 10 = 250 → issued → dispensed.
   3.  Lab: test priced 200 → ordered → collected → in_progress →
       result → result_ready → reviewed.
   4.  POST /invoices with visit_id → auto-aggregates 500 + 250 + 200
       = 950 subtotal/total, status 'draft'.
   5.  GET /invoices/{id} → 3 line items, total 950, balance_due 950.
   6.  PATCH status draft→unpaid (finalize, items locked).
   7.  POST /items on an 'unpaid' invoice → 400.
   8.  POST /payments 400 cash → status 'partial', balance_due 550.
   9.  POST /payments 550 card ref=TXN123 → status 'paid',
       balance_due 0, paid_at stamped.
   10. POST /payments 100 on a 'paid' invoice → 400 (overpay).
   11. Refund: POST /payments -100 → balance_due 100, status stays
       'paid' (a refund never demotes status).
   12. GET /billing/outstanding → includes the refunded invoice
       (balance_due > 0).
   13. GET /billing/revenue today → gross 950, refunds 100, net 850.
   14. Cross-tenant 404; Decimal exactness (qty 3 x 33.33 = 99.99 in
       DB and JSON); manual invoice with no visit; cancel a draft
       invoice (204); cancel a 'paid' invoice (400).
   (cleanup) Demote the test user back to non-super.
"""

import asyncio
import sys
import uuid
from datetime import date
from decimal import Decimal

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.database import AsyncSessionLocal  # noqa: F401 — ensures models register
from app.utils.security import hash_password


DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"
SEED_HOSPITAL_SLUG = "smoke11-platform"


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


def _dec(value) -> Decimal:
    """Coerce a JSON money field (string or number) to an exact Decimal
    without float drift."""
    return Decimal(str(value))


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
            "VALUES ('Smoke11 Platform', $1, 'UTC') RETURNING id",
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
    slug = f"smoke11-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase11 {label.title()}",
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
        json={"first_name": "Patient", "last_name": "Eleven"},
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
            # 1. Bootstrap hospital A + doctor + patient + active visit
            # ============================================================
            hospital_a, hdrs_a = await _bootstrap_hospital(c, super_hdrs, "a")
            doctor_a = await _make_doctor(c, hdrs_a, "drbill")
            # Set the consultation fee directly — auto-aggregation reads it.
            await pg.execute(
                "UPDATE doctor_profiles SET consultation_fee=500 WHERE id=$1",
                uuid.UUID(doctor_a),
            )
            patient_a = await _make_patient(c, hdrs_a)
            visit_a = await _make_visit(c, hdrs_a, patient_a, doctor_a)
            await _say(
                True,
                "1. hospital A + doctor (fee=500) + patient + active visit ready",
            )

            # ============================================================
            # 2. Prescription — drug @ 25 x 10 = 250 → issued → dispensed
            # ============================================================
            r = await c.post(
                "/api/v1/drugs",
                json={"name": "Amoxicillin 250mg", "form": "capsule",
                      "unit_price": "25.00"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create drug: {r.text[:200]}"
            drug_a = r.json()["id"]

            r = await c.post(
                f"/api/v1/drugs/{drug_a}/batches",
                json={
                    "batch_number": "AMOX-1",
                    "expiry_date": date(today.year + 1, today.month, 1).isoformat(),
                    "stock_quantity": 50,
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"add batch: {r.text[:200]}"

            r = await c.post(
                f"/api/v1/visits/{visit_a}/prescriptions",
                json={"items": [{"drug_id": drug_a, "quantity": 10}]},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create prescription: {r.text[:200]}"
            rx_a = r.json()["id"]
            rx_item = r.json()["items"][0]["id"]

            r = await c.patch(
                f"/api/v1/prescriptions/{rx_a}",
                json={"status": "issued"},
                headers=hdrs_a,
            )
            assert r.status_code == 200, f"issue prescription: {r.text[:200]}"

            r = await c.post(
                f"/api/v1/prescriptions/{rx_a}/items/{rx_item}/dispense",
                json={"quantity": 10},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"dispense: {r.text[:200]}"
            await _say(
                r.json()["prescription_status"] == "dispensed",
                "2. prescription (10 x 25 = 250) issued and dispensed",
            )

            # ============================================================
            # 3. Lab — test priced 200 → ordered → ... → reviewed
            # ============================================================
            r = await c.post(
                "/api/v1/lab-tests",
                json={"name": "CBC", "category": "Hematology", "price": "200.00"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create lab test: {r.text[:200]}"
            test_a = r.json()["id"]

            r = await c.post(
                f"/api/v1/visits/{visit_a}/lab-orders",
                json={"test_id": test_a},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"order lab: {r.text[:200]}"
            order_a = r.json()["id"]

            for step in ("collected", "in_progress"):
                r = await c.patch(
                    f"/api/v1/lab-orders/{order_a}",
                    json={"status": step},
                    headers=hdrs_a,
                )
                assert r.status_code == 200, f"lab→{step}: {r.text[:200]}"
            r = await c.post(
                f"/api/v1/lab-orders/{order_a}/result",
                json={"result_value": "Normal", "is_abnormal": False},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"lab result: {r.text[:200]}"
            for step in ("result_ready", "reviewed"):
                r = await c.patch(
                    f"/api/v1/lab-orders/{order_a}",
                    json={"status": step},
                    headers=hdrs_a,
                )
                assert r.status_code == 200, f"lab→{step}: {r.text[:200]}"
            await _say(True, "3. lab order (priced 200) completed and reviewed")

            # ============================================================
            # 4. Auto-aggregate invoice from the visit
            # ============================================================
            r = await c.post(
                "/api/v1/invoices",
                json={"visit_id": visit_a},
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 201
                and body["status"] == "draft"
                and _dec(body["subtotal"]) == Decimal("950.00")
                and _dec(body["total_amount"]) == Decimal("950.00"),
                f"4. auto-invoice from visit → {r.status_code}, subtotal="
                f"{body.get('subtotal')}, total={body.get('total_amount')} "
                f"(expected 950.00)",
            )
            invoice_a = body["id"]

            # ============================================================
            # 5. GET invoice — 3 lines, balance_due 950
            # ============================================================
            r = await c.get(f"/api/v1/invoices/{invoice_a}", headers=hdrs_a)
            body = r.json()
            await _say(
                r.status_code == 200
                and len(body["items"]) == 3
                and _dec(body["total_amount"]) == Decimal("950.00")
                and _dec(body["balance_due"]) == Decimal("950.00")
                and _dec(body["amount_paid"]) == Decimal("0.00"),
                f"5. GET invoice → {len(body.get('items', []))} items, "
                f"balance_due={body.get('balance_due')} (expected 950.00)",
            )

            # ============================================================
            # 6. Finalize: draft → unpaid
            # ============================================================
            r = await c.patch(
                f"/api/v1/invoices/{invoice_a}",
                json={"status": "unpaid"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 200 and r.json()["status"] == "unpaid",
                f"6. PATCH draft→unpaid (finalize) → {r.status_code}",
            )

            # ============================================================
            # 7. Add a line item to a finalized invoice → 400
            # ============================================================
            r = await c.post(
                f"/api/v1/invoices/{invoice_a}/items",
                json={"description": "Late charge", "quantity": 1,
                      "unit_price": "10.00"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"7. POST item on a non-draft invoice → {r.status_code}",
            )

            # ============================================================
            # 8. Partial payment — 400 cash
            # ============================================================
            r = await c.post(
                f"/api/v1/invoices/{invoice_a}/payments",
                json={"amount": "400.00", "method": "cash"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"payment 1: {r.text[:200]}"
            r = await c.get(f"/api/v1/invoices/{invoice_a}", headers=hdrs_a)
            body = r.json()
            await _say(
                body["status"] == "partial"
                and _dec(body["balance_due"]) == Decimal("550.00")
                and _dec(body["amount_paid"]) == Decimal("400.00"),
                f"8. pay 400 cash → status={body.get('status')}, "
                f"balance_due={body.get('balance_due')} (expected 550.00)",
            )

            # ============================================================
            # 9. Final payment — 550 card → paid
            # ============================================================
            r = await c.post(
                f"/api/v1/invoices/{invoice_a}/payments",
                json={"amount": "550.00", "method": "card", "reference": "TXN123"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"payment 2: {r.text[:200]}"
            r = await c.get(f"/api/v1/invoices/{invoice_a}", headers=hdrs_a)
            body = r.json()
            await _say(
                body["status"] == "paid"
                and _dec(body["balance_due"]) == Decimal("0.00")
                and body["paid_at"] is not None,
                f"9. pay 550 card → status={body.get('status')}, "
                f"balance_due={body.get('balance_due')}, paid_at stamped",
            )

            # ============================================================
            # 10. Overpay a paid invoice → 400
            # ============================================================
            r = await c.post(
                f"/api/v1/invoices/{invoice_a}/payments",
                json={"amount": "100.00", "method": "cash"},
                headers=hdrs_a,
            )
            await _say(
                r.status_code == 400,
                f"10. overpay a 'paid' invoice → {r.status_code}",
            )

            # ============================================================
            # 11. Refund — negative payment, status stays 'paid'
            # ============================================================
            r = await c.post(
                f"/api/v1/invoices/{invoice_a}/payments",
                json={"amount": "-100.00", "method": "cash"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"refund: {r.text[:200]}"
            r = await c.get(f"/api/v1/invoices/{invoice_a}", headers=hdrs_a)
            body = r.json()
            await _say(
                body["status"] == "paid"
                and _dec(body["balance_due"]) == Decimal("100.00")
                and _dec(body["amount_paid"]) == Decimal("850.00"),
                f"11. refund 100 → balance_due={body.get('balance_due')} "
                f"(expected 100.00), status stays '{body.get('status')}'",
            )

            # ============================================================
            # 12. Outstanding report includes the refunded invoice
            # ============================================================
            r = await c.get("/api/v1/billing/outstanding", headers=hdrs_a)
            outstanding_ids = {inv["id"] for inv in r.json()}
            await _say(
                r.status_code == 200 and invoice_a in outstanding_ids,
                f"12. GET /billing/outstanding includes the invoice "
                f"(balance_due > 0) → {len(r.json())} invoice(s)",
            )

            # ============================================================
            # 13. Revenue report — gross 950, refunds 100, net 850
            # ============================================================
            r = await c.get(
                f"/api/v1/billing/revenue?from_date={today.isoformat()}"
                f"&to_date={today.isoformat()}",
                headers=hdrs_a,
            )
            body = r.json()
            await _say(
                r.status_code == 200
                and _dec(body["gross"]) == Decimal("950.00")
                and _dec(body["refunds"]) == Decimal("100.00")
                and _dec(body["net"]) == Decimal("850.00"),
                f"13. revenue report → gross={body.get('gross')}, "
                f"refunds={body.get('refunds')}, net={body.get('net')} "
                f"(expected 950.00 / 100.00 / 850.00)",
            )

            # ============================================================
            # 14a. Cross-tenant isolation
            # ============================================================
            hospital_b, hdrs_b = await _bootstrap_hospital(c, super_hdrs, "b")
            r1 = await c.get(f"/api/v1/invoices/{invoice_a}", headers=hdrs_b)
            r2 = await c.get(
                f"/api/v1/invoices/{invoice_a}/payments", headers=hdrs_b
            )
            await _say(
                r1.status_code == 404 and r2.status_code == 404,
                "14a. hospital B cannot read A's invoice or payments → 404",
            )

            # ============================================================
            # 14b. Decimal exactness + manual invoice with no visit
            # ============================================================
            r = await c.post(
                "/api/v1/invoices",
                json={
                    "patient_id": patient_a,
                    "items": [
                        {"description": "Precision test", "quantity": 3,
                         "unit_price": "33.33"},
                    ],
                },
                headers=hdrs_a,
            )
            body = r.json()
            json_line_ok = (
                r.status_code == 201
                and _dec(body["items"][0]["total_price"]) == Decimal("99.99")
                and _dec(body["total_amount"]) == Decimal("99.99")
            )
            manual_invoice = body["id"]
            db_total = await pg.fetchval(
                "SELECT total_price FROM invoice_items WHERE invoice_id=$1",
                uuid.UUID(manual_invoice),
            )
            await _say(
                json_line_ok and db_total == Decimal("99.99"),
                f"14b. manual invoice (no visit) — 3 x 33.33: "
                f"JSON total_price={body['items'][0]['total_price']}, "
                f"DB total_price={db_total} (both expected 99.99)",
            )

            # ============================================================
            # 14c. Cancel a draft invoice → 204
            # ============================================================
            r = await c.delete(
                f"/api/v1/invoices/{manual_invoice}", headers=hdrs_a
            )
            await _say(
                r.status_code == 204,
                f"14c. DELETE a 'draft' invoice → {r.status_code}",
            )

            # ============================================================
            # 14d. Cancel a 'paid' invoice → 400
            # ============================================================
            r = await c.delete(f"/api/v1/invoices/{invoice_a}", headers=hdrs_a)
            await _say(
                r.status_code == 400,
                f"14d. DELETE a 'paid' invoice → {r.status_code}",
            )

        # ============================================================
        # Cleanup — demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "cleanup: test user demoted from super_admin")

        print("\n========== PHASE 11 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 11 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

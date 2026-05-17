"""
Phase 13 end-to-end smoke test — Audit Logging.

Runs against the live Postgres on port 5433. Drives FastAPI in-process
via httpx.AsyncClient + ASGITransport (no uvicorn needed). The test
user is temporarily promoted to super_admin so we can bootstrap fresh
hospitals, then demoted at the end.

Audit rows are verified two ways: through the GET /audit-logs read
endpoints, and by querying the audit_logs table directly with asyncpg
(JSONB columns come back as strings — json.loads is applied).

Test cases (printed [PASS] / [FAIL]):
   1.  Bootstrap hospital A + admin + doctor + patient + active visit.
   2.  Login → an audit row with action='login' for that user.
   3.  Wrong password → an audit row with action='login_failed'.
   4.  5 wrong passwords → an audit row with action='account_locked'.
   5.  Dispense a prescription item → action='dispense', and
       new_value carries a STRING batch_id (JSONB sanitizer check).
   6.  Record a payment → action='record_payment', new_value carries
       amount + method.
   7.  Deactivate a membership → action='deactivate_membership'.
   8.  Cancel a prescription → action='cancel_prescription'.
   9.  GET /audit-logs as a hospital admin → rows scoped to that
       hospital only.
   10. GET /audit-logs as a super-admin → login events (hospital_id
       NULL) visible to super-admin but NOT to the hospital admin.
   11. GET /audit-logs/entity/prescription_item/{id} → the dispense
       history; GET /audit-logs/{id} resolves the single entry.
   12. Cross-tenant: hospital B admin sees none of A's audit logs
       (empty entity history; 404 on A's entry id).
   13. Non-admin (a doctor) GET /audit-logs → 403.
   14. Atomic rollback: a failing dispense writes NO audit row — the
       audit-row count for the item is unchanged across the failure.
   (cleanup) Demote the test user back to non-super.
"""

import asyncio
import json
import sys
import uuid
from datetime import date

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.database import AsyncSessionLocal  # noqa: F401 — ensures models register
from app.utils.security import hash_password


DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"
SEED_HOSPITAL_SLUG = "smoke13-platform"


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


# ----------------------------------------------------------------
# AUDIT-TABLE INSPECTION (asyncpg direct)
# ----------------------------------------------------------------

def _where(filt: dict):
    clauses, args = [], []
    for key, value in filt.items():
        args.append(value)
        clauses.append(f"{key} = ${len(args)}")
    sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    return sql, args


async def _count_audit(pg: asyncpg.Connection, **filt) -> int:
    sql, args = _where(filt)
    return await pg.fetchval(f"SELECT count(*) FROM audit_logs{sql}", *args)


async def _latest_audit(pg: asyncpg.Connection, **filt):
    sql, args = _where(filt)
    return await pg.fetchrow(
        f"SELECT * FROM audit_logs{sql} ORDER BY created_at DESC LIMIT 1", *args
    )


def _json(value):
    """asyncpg returns JSONB columns as strings — decode to a dict."""
    return json.loads(value) if value else None


# ----------------------------------------------------------------
# SEED + BOOTSTRAP
# ----------------------------------------------------------------

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
            "VALUES ('Smoke13 Platform', $1, 'UTC') RETURNING id",
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
            "is_active=true, deleted_at=NULL, failed_login_attempts=0, "
            "locked_until=NULL WHERE id=$1",
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
    slug = f"smoke13-{label}-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin-{label}-{uuid.uuid4().hex[:6]}@smoke.dev"
    admin_password = "Bootstrap1!"

    r = await c.post(
        "/api/v1/admin/hospitals",
        json={
            "name": f"Smoke Phase13 {label.title()}",
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
    """Invite + accept + login a hospital member.
    Returns (user_id, headers, email, password)."""
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
    return (
        user_id,
        {"Authorization": f"Bearer {r.json()['access_token']}"},
        email,
        password,
    )


async def _make_doctor(c: httpx.AsyncClient, hdrs: dict, hospital_id: str, label: str):
    """Invite a doctor user + create their doctor profile; return profile id."""
    user_id, _, _, _ = await _make_member(c, hdrs, hospital_id, "doctor", label)
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
        json={"first_name": "Patient", "last_name": "Thirteen"},
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
            "chief_complaint": "Headache",
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


async def _issued_prescription(
    c: httpx.AsyncClient, hdrs: dict, visit_id: str
):
    """Create a drug + batch + a one-item prescription, advance it to
    'issued'. Returns (prescription_id, item_id, batch_id)."""
    r = await c.post(
        "/api/v1/drugs",
        json={"name": f"AuditDrug {uuid.uuid4().hex[:6]}", "form": "tablet"},
        headers=hdrs,
    )
    assert r.status_code == 201, f"create drug: {r.text[:200]}"
    drug_id = r.json()["id"]

    r = await c.post(
        f"/api/v1/drugs/{drug_id}/batches",
        json={
            "batch_number": f"AUD-{uuid.uuid4().hex[:6]}",
            "expiry_date": date(date.today().year + 1, 12, 31).isoformat(),
            "stock_quantity": 50,
        },
        headers=hdrs,
    )
    assert r.status_code == 201, f"add batch: {r.text[:200]}"
    batch_id = r.json()["id"]

    r = await c.post(
        f"/api/v1/visits/{visit_id}/prescriptions",
        json={"items": [{"drug_id": drug_id, "quantity": 10}]},
        headers=hdrs,
    )
    assert r.status_code == 201, f"create prescription: {r.text[:200]}"
    prescription_id = r.json()["id"]
    item_id = r.json()["items"][0]["id"]

    r = await c.patch(
        f"/api/v1/prescriptions/{prescription_id}",
        json={"status": "issued"},
        headers=hdrs,
    )
    assert r.status_code == 200, f"issue prescription: {r.text[:200]}"
    return prescription_id, item_id, batch_id


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
            hospital_a, hdrs_a, admin_a_uid = await _bootstrap_hospital(
                c, super_hdrs, "a"
            )
            doctor_a = await _make_doctor(c, hdrs_a, hospital_a, "drcare")
            patient_a = await _make_patient(c, hdrs_a)
            visit_a = await _make_visit(c, hdrs_a, patient_a, doctor_a)
            await _say(
                True, "1. hospital A + doctor + patient + active visit ready"
            )

            # ============================================================
            # 2. Login success → action='login'
            # ============================================================
            loginee_uid, _, loginee_email, loginee_pw = await _make_member(
                c, hdrs_a, hospital_a, "nurse", "loginee"
            )
            before = await _count_audit(
                pg, action="login", user_id=uuid.UUID(loginee_uid)
            )
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": loginee_email, "password": loginee_pw},
            )
            after = await _count_audit(
                pg, action="login", user_id=uuid.UUID(loginee_uid)
            )
            await _say(
                r.status_code == 200 and after == before + 1,
                f"2. login success → action='login' rows {before}→{after} "
                f"(expected +1)",
            )

            # ============================================================
            # 3. Login failure → action='login_failed'
            # ============================================================
            before = await _count_audit(
                pg, action="login_failed", user_id=uuid.UUID(loginee_uid)
            )
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": loginee_email, "password": "WrongPass9!"},
            )
            after = await _count_audit(
                pg, action="login_failed", user_id=uuid.UUID(loginee_uid)
            )
            row = await _latest_audit(
                pg, action="login_failed", user_id=uuid.UUID(loginee_uid)
            )
            reason = (_json(row["new_value"]) or {}).get("reason")
            await _say(
                r.status_code == 401
                and after == before + 1
                and reason == "wrong_password",
                f"3. wrong password → 401, action='login_failed' rows "
                f"{before}→{after}, reason={reason!r}",
            )

            # ============================================================
            # 4. Repeated failures → action='account_locked'
            # ============================================================
            victim_uid, _, victim_email, _ = await _make_member(
                c, hdrs_a, hospital_a, "receptionist", "victim"
            )
            for _ in range(5):
                await c.post(
                    "/api/v1/auth/login",
                    json={"email": victim_email, "password": "DefinitelyWrong1!"},
                )
            locked = await _count_audit(
                pg, action="account_locked", user_id=uuid.UUID(victim_uid)
            )
            failed = await _count_audit(
                pg, action="login_failed", user_id=uuid.UUID(victim_uid)
            )
            await _say(
                locked == 1 and failed == 5,
                f"4. 5 wrong passwords → account_locked rows={locked} "
                f"(expected 1), login_failed rows={failed} (expected 5)",
            )

            # ============================================================
            # 5. Dispense → action='dispense' + JSONB sanitizer check
            # ============================================================
            rx_a, item_a, batch_a = await _issued_prescription(c, hdrs_a, visit_a)
            r = await c.post(
                f"/api/v1/prescriptions/{rx_a}/items/{item_a}/dispense",
                json={"quantity": 5},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"dispense: {r.text[:200]}"
            row = await _latest_audit(
                pg, action="dispense", resource_id=uuid.UUID(item_a)
            )
            nv = _json(row["new_value"]) if row else None
            sanitizer_ok = (
                nv is not None
                and isinstance(nv.get("batch_id"), str)
                and nv["batch_id"] == batch_a
                and nv.get("quantity") == 5
            )
            await _say(
                row is not None
                and row["resource_type"] == "prescription_item"
                and str(row["hospital_id"]) == hospital_a
                and sanitizer_ok,
                f"5. dispense → action='dispense', new_value batch_id is a "
                f"string ({sanitizer_ok}), quantity={nv.get('quantity') if nv else None}",
            )

            # ============================================================
            # 6. Record payment → action='record_payment'
            # ============================================================
            r = await c.post(
                "/api/v1/invoices",
                json={
                    "patient_id": patient_a,
                    "items": [
                        {
                            "description": "Consultation fee",
                            "quantity": 1,
                            "unit_price": "500.00",
                        }
                    ],
                },
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create invoice: {r.text[:200]}"
            invoice_a = r.json()["id"]
            r = await c.patch(
                f"/api/v1/invoices/{invoice_a}",
                json={"status": "unpaid"},
                headers=hdrs_a,
            )
            assert r.status_code == 200, f"finalize invoice: {r.text[:200]}"
            r = await c.post(
                f"/api/v1/invoices/{invoice_a}/payments",
                json={"amount": "500.00", "method": "cash"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"record payment: {r.text[:200]}"
            row = await _latest_audit(
                pg, action="record_payment", resource_id=uuid.UUID(invoice_a)
            )
            nv = _json(row["new_value"]) if row else None
            await _say(
                row is not None
                and row["resource_type"] == "invoice"
                and nv is not None
                and nv.get("amount") == "500.00"
                and nv.get("method") == "cash"
                and nv.get("is_refund") is False,
                f"6. record payment → action='record_payment', "
                f"new_value amount={nv.get('amount') if nv else None}, "
                f"method={nv.get('method') if nv else None}",
            )

            # ============================================================
            # 7. Deactivate a membership → action='deactivate_membership'
            # ============================================================
            removee_uid, _, _, _ = await _make_member(
                c, hdrs_a, hospital_a, "nurse", "removee"
            )
            before = await _count_audit(
                pg, action="deactivate_membership", hospital_id=uuid.UUID(hospital_a)
            )
            r = await c.delete(
                f"/api/v1/users/{removee_uid}", headers=hdrs_a
            )
            after = await _count_audit(
                pg, action="deactivate_membership", hospital_id=uuid.UUID(hospital_a)
            )
            await _say(
                r.status_code == 204 and after == before + 1,
                f"7. deactivate membership → {r.status_code}, "
                f"action='deactivate_membership' rows {before}→{after}",
            )

            # ============================================================
            # 8. Cancel a prescription → action='cancel_prescription'
            # ============================================================
            r = await c.post(
                "/api/v1/drugs",
                json={"name": f"CancelDrug {uuid.uuid4().hex[:6]}", "form": "tablet"},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create cancel drug: {r.text[:200]}"
            cancel_drug = r.json()["id"]
            r = await c.post(
                f"/api/v1/visits/{visit_a}/prescriptions",
                json={"items": [{"drug_id": cancel_drug, "quantity": 1}]},
                headers=hdrs_a,
            )
            assert r.status_code == 201, f"create cancel rx: {r.text[:200]}"
            cancel_rx = r.json()["id"]
            r = await c.patch(
                f"/api/v1/prescriptions/{cancel_rx}",
                json={"status": "cancelled"},
                headers=hdrs_a,
            )
            row = await _latest_audit(
                pg, action="cancel_prescription", resource_id=uuid.UUID(cancel_rx)
            )
            ov = _json(row["old_value"]) if row else None
            await _say(
                r.status_code == 200
                and row is not None
                and row["resource_type"] == "prescription"
                and ov is not None
                and ov.get("status") == "draft",
                f"8. cancel prescription → action='cancel_prescription', "
                f"old_value status={ov.get('status') if ov else None}",
            )

            # ============================================================
            # 9. GET /audit-logs as hospital admin → scoped to A
            # ============================================================
            r = await c.get(
                "/api/v1/audit-logs?action=dispense", headers=hdrs_a
            )
            body = r.json()
            all_scoped = all(
                it["hospital_id"] == hospital_a for it in body["items"]
            )
            await _say(
                r.status_code == 200
                and body["total"] >= 1
                and all_scoped,
                f"9. hospital admin GET /audit-logs?action=dispense → "
                f"total={body.get('total')}, all rows scoped to A ({all_scoped})",
            )

            # ============================================================
            # 10. Super-admin sees login events; hospital admin does not
            # ============================================================
            r_super = await c.get(
                "/api/v1/audit-logs?action=login", headers=super_hdrs
            )
            r_admin = await c.get(
                "/api/v1/audit-logs?action=login", headers=hdrs_a
            )
            await _say(
                r_super.status_code == 200
                and r_super.json()["total"] >= 1
                and r_admin.status_code == 200
                and r_admin.json()["total"] == 0,
                f"10. login events: super-admin sees "
                f"{r_super.json()['total']} (>=1), hospital admin sees "
                f"{r_admin.json()['total']} (expected 0 — hospital_id NULL)",
            )

            # ============================================================
            # 11. Resource history + single-entry lookup
            # ============================================================
            r = await c.get(
                f"/api/v1/audit-logs/entity/prescription_item/{item_a}",
                headers=hdrs_a,
            )
            body = r.json()
            has_dispense = any(
                it["action"] == "dispense" for it in body["items"]
            )
            entry_id = body["items"][0]["id"] if body["items"] else None
            r2 = await c.get(
                f"/api/v1/audit-logs/{entry_id}", headers=hdrs_a
            )
            await _say(
                r.status_code == 200
                and has_dispense
                and r2.status_code == 200
                and r2.json()["id"] == entry_id,
                f"11. entity history for the item → {len(body['items'])} "
                f"row(s), dispense present ({has_dispense}); "
                f"GET /audit-logs/{{id}} → {r2.status_code}",
            )

            # ============================================================
            # 12. Cross-tenant — hospital B sees none of A's audit logs
            # ============================================================
            hospital_b, hdrs_b, _ = await _bootstrap_hospital(c, super_hdrs, "b")
            r1 = await c.get(
                f"/api/v1/audit-logs/entity/prescription_item/{item_a}",
                headers=hdrs_b,
            )
            r2 = await c.get(
                f"/api/v1/audit-logs/{entry_id}", headers=hdrs_b
            )
            await _say(
                r1.status_code == 200
                and len(r1.json()["items"]) == 0
                and r2.status_code == 404,
                f"12. hospital B reads A's audit history → "
                f"entity={r1.status_code}/{len(r1.json()['items'])} items, "
                f"single entry={r2.status_code} (expected 200/0 and 404)",
            )

            # ============================================================
            # 13. Non-admin (a doctor) GET /audit-logs → 403
            # ============================================================
            _, doctor_hdrs, _, _ = await _make_member(
                c, hdrs_a, hospital_a, "doctor", "nosey"
            )
            r = await c.get("/api/v1/audit-logs", headers=doctor_hdrs)
            await _say(
                r.status_code == 403,
                f"13. doctor GET /audit-logs → {r.status_code} (expected 403)",
            )

            # ============================================================
            # 14. Atomic rollback — a failing dispense writes NO audit row
            # ============================================================
            before = await _count_audit(
                pg, action="dispense", resource_id=uuid.UUID(item_a)
            )
            r = await c.post(
                f"/api/v1/prescriptions/{rx_a}/items/{item_a}/dispense",
                json={"quantity": 9999},
                headers=hdrs_a,
            )
            after = await _count_audit(
                pg, action="dispense", resource_id=uuid.UUID(item_a)
            )
            await _say(
                r.status_code == 422 and before == after,
                f"14. failing dispense → {r.status_code}; audit rows for the "
                f"item unchanged ({before}→{after}) — rollback held",
            )

        # ============================================================
        # Cleanup — demote test user
        # ============================================================
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1", TEST_USER_EMAIL
        )
        await _say(True, "cleanup: test user demoted from super_admin")

        print("\n========== PHASE 13 SMOKE: ALL TESTS PASSED ==========")
    finally:
        await pg.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        print(f"\n========== PHASE 13 SMOKE: FAILED (exit {e.code}) ==========")
        sys.exit(e.code or 1)

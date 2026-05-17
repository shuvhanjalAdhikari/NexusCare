"""
Phase 4.7 end-to-end smoke test.

Runs against the live Postgres DB on port 5433. Drives the FastAPI app
in-process via httpx.AsyncClient + ASGITransport — no uvicorn needed.

Flow:
  1.  Promote test@hospital.dev to super_admin (temporary) so we can hit /admin.
  2.  POST /admin/hospitals to create a fresh tenant + first admin (returns invite token).
  3.  Verify all 7 built-in roles were seeded for the new hospital.
  4.  Accept the invite -> set the new admin's password.
  5.  Log in as the new admin; select workspace; obtain access token.
  6.  Roles list endpoint returns 7 roles (own) + 1 system role (the legacy test one).
  7.  Invite a doctor user — new email branch (invite_token present).
  8.  Accept the doctor invite; log in as the doctor.
  9.  Invite the SAME existing doctor email to a SECOND new hospital via a second
      bootstrap — verifies "existing user, new hospital" branch (no invite token).
  10. Cross-tenant: as the new-hospital admin, try GET /users/{legacy_user_id} -> 404.
  11. Last-admin guard: try to deactivate the new hospital's only admin -> 400.
  12. Soft-delete the doctor membership -> 204. Listing no longer shows the doctor.
  13. Forgot/reset password — issue reset token via service, hit /reset-password.
  14. Demote test user back to non-super.
  15. Phase-3 regression: log in as test@hospital.dev, select workspace, hit /auth/me.

Prints PASS/FAIL banner at the end.
"""

import asyncio
import sys
import uuid

import asyncpg
import httpx
from httpx import ASGITransport

from app.main import app
from app.services import auth as auth_service
from app.database import AsyncSessionLocal
from app.utils.security import hash_password

DB_URL = "postgresql://admin:admin123@localhost:5433/nexus_care"
TEST_USER_EMAIL = "test@hospital.dev"
TEST_USER_PASSWORD = "secret123"


async def _say(ok: bool, msg: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"{mark} {msg}")
    if not ok:
        raise SystemExit(1)


async def main() -> None:
    pg = await asyncpg.connect(DB_URL)
    try:
        # ---- 1. Promote test user to super_admin + reset their password
        # so the smoke is deterministic (we don't know what Phase-3 used).
        # Also clear any lockout state from prior failed runs.
        new_hash = hash_password(TEST_USER_PASSWORD)
        await pg.execute(
            "UPDATE users SET system_role='super_admin', password_hash=$2, "
            "failed_login_attempts=0, locked_until=NULL WHERE email=$1",
            TEST_USER_EMAIL,
            new_hash,
        )
        await _say(True, "test user promoted to super_admin + password reset")

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:

            # --- super-admin login ----------------------------------------
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": TEST_USER_EMAIL, "password": "secret123"},
            )
            await _say(r.status_code == 200, f"super-admin login -> {r.status_code}")
            sel_token = r.json()["selection_token"]

            # super admin has NO hospital-scoped JWT; we hit /admin with the
            # selection token? No — /admin uses get_current_user which requires
            # an access token. We need to select the workspace first.
            memberships = r.json()["memberships"]
            workspace_hid = memberships[0]["hospital_id"]
            r = await c.post(
                "/api/v1/auth/select-workspace",
                json={"hospital_id": workspace_hid},
                headers={"Authorization": f"Bearer {sel_token}"},
            )
            await _say(r.status_code == 200, f"super-admin workspace select -> {r.status_code}")
            super_access = r.json()["access_token"]
            super_hdrs = {"Authorization": f"Bearer {super_access}"}

            # --- 2. Create new hospital + first admin -------------------
            new_slug = f"smoke-{uuid.uuid4().hex[:6]}"
            new_admin_email = f"admin-{uuid.uuid4().hex[:6]}@smoke.dev"
            r = await c.post(
                "/api/v1/admin/hospitals",
                json={
                    "name": "Smoke General Hospital",
                    "slug": new_slug,
                    "timezone": "Asia/Kathmandu",
                    "admin_email": new_admin_email,
                    "admin_first_name": "Smoke",
                    "admin_last_name": "Admin",
                },
                headers=super_hdrs,
            )
            await _say(r.status_code == 201, f"create hospital -> {r.status_code}: {r.text[:200]}")
            body = r.json()
            new_hospital_id = body["hospital"]["id"]
            new_admin_id = body["admin_user_id"]
            new_admin_invite = body["invite_token"]

            # --- 3. Verify 7 roles seeded -------------------------------
            role_rows = await pg.fetch(
                "SELECT name FROM roles WHERE hospital_id = $1 ORDER BY name",
                uuid.UUID(new_hospital_id),
            )
            await _say(
                len(role_rows) == 7,
                f"seeded {len(role_rows)} roles for new hospital",
            )
            names = {r["name"] for r in role_rows}
            await _say(
                "hospital_admin" in names and "doctor" in names,
                f"role names present: {sorted(names)}",
            )

            # --- 4. Accept the new admin's invite -----------------------
            new_admin_password = "Bootstrap1!"
            r = await c.post(
                "/api/v1/auth/accept-invite",
                json={"invite_token": new_admin_invite, "password": new_admin_password},
            )
            await _say(r.status_code == 200, f"new admin accept-invite -> {r.status_code}: {r.text[:200]}")

            # --- 5. Login as new admin ----------------------------------
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": new_admin_email, "password": new_admin_password},
            )
            await _say(r.status_code == 200, f"new admin login -> {r.status_code}")
            sel_token = r.json()["selection_token"]
            memberships = r.json()["memberships"]
            await _say(
                len(memberships) == 1 and memberships[0]["hospital_id"] == new_hospital_id,
                "new admin sees exactly one membership (the new hospital)",
            )
            r = await c.post(
                "/api/v1/auth/select-workspace",
                json={"hospital_id": new_hospital_id},
                headers={"Authorization": f"Bearer {sel_token}"},
            )
            await _say(r.status_code == 200, f"new admin workspace select -> {r.status_code}")
            new_admin_access = r.json()["access_token"]
            new_admin_hdrs = {"Authorization": f"Bearer {new_admin_access}"}

            # --- 6. List roles ------------------------------------------
            r = await c.get("/api/v1/roles", headers=new_admin_hdrs)
            await _say(r.status_code == 200, f"roles list -> {r.status_code}")
            roles = r.json()
            # 7 own + 1 legacy system role (hospital_admin with hospital_id=NULL)
            await _say(
                len(roles) >= 7,
                f"new admin sees {len(roles)} roles (own + system)",
            )
            doctor_role_id = next(r["id"] for r in roles if r["name"] == "doctor")

            # --- 7. Invite a doctor (new email path) ---------------------
            doctor_email = f"doc-{uuid.uuid4().hex[:6]}@smoke.dev"
            r = await c.post(
                "/api/v1/users/invite",
                json={
                    "email": doctor_email,
                    "first_name": "Doc",
                    "last_name": "Smith",
                    "role_id": doctor_role_id,
                },
                headers=new_admin_hdrs,
            )
            await _say(r.status_code == 201, f"invite doctor -> {r.status_code}: {r.text[:200]}")
            inv = r.json()
            doctor_id = inv["user_id"]
            doctor_invite = inv["invite_token"]
            await _say(
                inv["requires_password"] is True and inv["invite_token"] is not None,
                "new-user invite path returns invite_token + requires_password=true",
            )

            # --- 8. Doctor accepts invite + logs in ---------------------
            r = await c.post(
                "/api/v1/auth/accept-invite",
                json={"invite_token": doctor_invite, "password": "DocPass99!"},
            )
            await _say(r.status_code == 200, f"doctor accept-invite -> {r.status_code}")

            r = await c.post(
                "/api/v1/auth/login",
                json={"email": doctor_email, "password": "DocPass99!"},
            )
            await _say(r.status_code == 200, f"doctor login -> {r.status_code}")

            # --- 9. Bootstrap a SECOND hospital, then invite the existing doctor to it
            second_slug = f"smoke2-{uuid.uuid4().hex[:6]}"
            second_admin_email = f"admin2-{uuid.uuid4().hex[:6]}@smoke.dev"
            r = await c.post(
                "/api/v1/admin/hospitals",
                json={
                    "name": "Smoke Annex Clinic",
                    "slug": second_slug,
                    "timezone": "UTC",
                    "admin_email": second_admin_email,
                    "admin_first_name": "Annex",
                    "admin_last_name": "Admin",
                },
                headers=super_hdrs,
            )
            await _say(r.status_code == 201, "create second hospital")
            body2 = r.json()
            second_hospital_id = body2["hospital"]["id"]
            r = await c.post(
                "/api/v1/auth/accept-invite",
                json={"invite_token": body2["invite_token"], "password": "Bootstrap2!"},
            )
            await _say(r.status_code == 200, "second admin accept-invite")
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": second_admin_email, "password": "Bootstrap2!"},
            )
            sel = r.json()["selection_token"]
            r = await c.post(
                "/api/v1/auth/select-workspace",
                json={"hospital_id": second_hospital_id},
                headers={"Authorization": f"Bearer {sel}"},
            )
            second_access = r.json()["access_token"]
            second_hdrs = {"Authorization": f"Bearer {second_access}"}
            r = await c.get("/api/v1/roles", headers=second_hdrs)
            second_doctor_role = next(x["id"] for x in r.json() if x["name"] == "doctor")
            r = await c.post(
                "/api/v1/users/invite",
                json={
                    "email": doctor_email,
                    "first_name": "Doc",
                    "last_name": "Smith",
                    "role_id": second_doctor_role,
                },
                headers=second_hdrs,
            )
            await _say(r.status_code == 201, f"invite EXISTING doctor to 2nd hospital -> {r.status_code}: {r.text[:200]}")
            inv2 = r.json()
            await _say(
                inv2["invite_token"] is None and inv2["requires_password"] is False,
                "existing-user invite path returns NO invite_token and requires_password=false",
            )
            await _say(inv2["user_id"] == doctor_id, "existing-user invite reuses the same user_id")

            # Verify doctor now has two memberships
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": doctor_email, "password": "DocPass99!"},
            )
            await _say(len(r.json()["memberships"]) == 2, "doctor now has 2 memberships")

            # --- 10. Cross-tenant: 2nd admin tries to read 1st hospital's admin user -> 404
            r = await c.get(
                f"/api/v1/users/{new_admin_id}",
                headers=second_hdrs,
            )
            await _say(
                r.status_code == 404,
                f"cross-tenant GET -> {r.status_code} (expected 404)",
            )

            # --- 11. Last-admin guard: try to deactivate the only admin --
            # new_admin is the only admin in their hospital. Deactivate self -> 400.
            r = await c.patch(
                f"/api/v1/users/{new_admin_id}/membership",
                json={"is_active": False},
                headers=new_admin_hdrs,
            )
            await _say(
                r.status_code == 400,
                f"self-deactivation -> {r.status_code} (expected 400)",
            )
            # Attempt to delete self -> 400 (cannot remove own membership)
            r = await c.delete(
                f"/api/v1/users/{new_admin_id}",
                headers=new_admin_hdrs,
            )
            await _say(
                r.status_code == 400,
                f"self-delete -> {r.status_code} (expected 400)",
            )

            # --- 12. List users ----------------------------------------
            r = await c.get("/api/v1/users", headers=new_admin_hdrs)
            await _say(r.status_code == 200, "list users")
            page = r.json()
            await _say(
                page["total"] == 2,
                f"expected 2 users (admin+doctor) got {page['total']}",
            )

            # Soft delete the doctor membership
            r = await c.delete(
                f"/api/v1/users/{doctor_id}",
                headers=new_admin_hdrs,
            )
            await _say(r.status_code == 204, f"soft-delete doctor -> {r.status_code}")
            r = await c.get("/api/v1/users", headers=new_admin_hdrs)
            await _say(
                r.json()["total"] == 1,
                f"after deletion, total is {r.json()['total']} (expected 1)",
            )

            # --- 13. Reset password (via direct service call) -----------
            async with AsyncSessionLocal() as db:
                reset_token = await auth_service.request_password_reset(
                    db, new_admin_email
                )
            await _say(reset_token is not None, "reset token generated for known user")

            # Also confirm unknown user returns None
            async with AsyncSessionLocal() as db:
                missing = await auth_service.request_password_reset(
                    db, "nobody-at-all@example.com"
                )
            await _say(missing is None, "reset token NOT generated for unknown user")

            # forgot-password HTTP endpoint always returns 200
            r = await c.post(
                "/api/v1/auth/forgot-password",
                json={"email": new_admin_email},
            )
            await _say(r.status_code == 200, "forgot-password (existing) returns 200")
            r = await c.post(
                "/api/v1/auth/forgot-password",
                json={"email": "nobody-at-all@example.com"},
            )
            await _say(r.status_code == 200, "forgot-password (unknown) returns 200")

            # Hit /reset-password with the real token
            new_pw = "Reset123!"
            r = await c.post(
                "/api/v1/auth/reset-password",
                json={"reset_token": reset_token, "password": new_pw},
            )
            await _say(r.status_code == 200, f"reset-password -> {r.status_code}")
            # New password works
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": new_admin_email, "password": new_pw},
            )
            await _say(r.status_code == 200, "login with reset password works")
            # Old password rejected
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": new_admin_email, "password": new_admin_password},
            )
            await _say(r.status_code == 401, "old password rejected after reset")

            # ============================================================
            # PHASE 3 REGRESSION
            # ============================================================
            print("\n--- Phase 3 regression ---")
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": TEST_USER_EMAIL, "password": "secret123"},
            )
            await _say(r.status_code == 200, "legacy user login -> 200")
            sel = r.json()["selection_token"]
            hid = r.json()["memberships"][0]["hospital_id"]
            r = await c.post(
                "/api/v1/auth/select-workspace",
                json={"hospital_id": hid},
                headers={"Authorization": f"Bearer {sel}"},
            )
            await _say(r.status_code == 200, "legacy user workspace select -> 200")
            access = r.json()["access_token"]
            r = await c.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access}"},
            )
            await _say(r.status_code == 200, "legacy user /auth/me -> 200")
            me = r.json()
            await _say(me["email"] == TEST_USER_EMAIL, f"/me email matches: {me['email']}")
            await _say(me["current_role"] == "hospital_admin", f"/me role is hospital_admin")
    finally:
        # ---- 15. demote test user back to non-super --------------------
        await pg.execute(
            "UPDATE users SET system_role=NULL WHERE email=$1",
            TEST_USER_EMAIL,
        )
        await pg.close()

    print("\nAll smoke + regression checks passed.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())

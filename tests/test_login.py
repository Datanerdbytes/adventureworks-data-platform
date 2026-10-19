"""Account authorization at real Flask/Dash boundaries; provider I/O is mocked."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from auth_fixtures import CONFIG, FakeGateway, csrf_headers, token


class LoginTests(unittest.TestCase):
    def setUp(self):
        app.server.extensions["auth_limiter"].reset()
        self.client = app.server.test_client()
        for mapping, values in (
            (app.server.config, CONFIG),
            (app.server.extensions, {"supabase_gateway_factory": FakeGateway}),
        ):
            item = patch.dict(mapping, values)
            item.start()
            self.addCleanup(item.stop)
        feature = patch("auth.ensure_not_locked")
        self.lock_check = feature.start()
        self.addCleanup(feature.stop)
        FakeGateway.calls = []

    def sync(self, kind="approved", next="/dashboard", lifetime=3600):
        return self.client.post(
            "/auth/session",
            json={"access_token": token(kind, lifetime), "next": next},
            headers=csrf_headers(self.client),
        )

    def test_confirmed_account_needs_no_membership_and_legacy_session_is_discarded(
        self,
    ):
        with self.client.session_transaction() as session:
            session["workspace_id"] = "legacy"
        for kind in ("no-member", "revoked", "viewer"):
            self.assertEqual(self.sync(kind).status_code, 200)
            self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        self.assertEqual(FakeGateway.calls, [])
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {})

    def test_public_auth_config_safe_next_and_cookie(self):
        for path in (
            "/login",
            "/signup",
            "/auth/recovery",
            "/auth/callback",
            "/auth/config",
        ):
            self.assertEqual(self.client.get(path).status_code, 200)
        response = self.sync(next="//attacker.test")
        self.assertEqual(response.json["next"], "/dashboard")
        cookie = next(
            c for c in response.headers.getlist("Set-Cookie") if "aw_access=" in c
        )
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertEqual(
            set(self.client.get("/auth/config").json),
            {"url", "publicKey", "providers", "passwordLockoutEnabled"},
        )
        self.assertNotIn("service", str(self.client.get("/auth/config").json).lower())

    def test_invalid_unconfirmed_suspended_expired_and_outage_fail_closed(self):
        for kind, expected in (
            ("expired", 401),
            ("tampered", 401),
            ("unconfirmed", 403),
            ("suspended", 403),
            ("outage", 503),
        ):
            self.sync()
            response = self.sync(kind)
            self.assertEqual(response.status_code, expected, kind)
            self.assertIsNone(self.client.get_cookie("aw_access"))
        self.assertEqual(self.sync(lifetime=-1).status_code, 401)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_current_suspension_and_lockout_are_checked_before_data_loads(self):
        from password_auth import PasswordAuthError

        self.sync()
        self.client.set_cookie("aw_access", token("suspended"))
        self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
        self.client.set_cookie("aw_access", token())
        for error, status in (
            (PasswordAuthError("account_locked", 423), 403),
            (PasswordAuthError("auth_unavailable"), 503),
        ):
            self.lock_check.side_effect = error
            self.assertEqual(self.client.get("/_dash-layout").status_code, status)

    def test_members_cannot_admin_even_with_forged_client_metadata(self):
        self.sync("viewer")
        for path in ("/admin/users", "/api/admin/users"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.client.get("/_dash-layout")
        key = "admin-users-page.data"
        body = {
            "output": key,
            "outputs": {"id": "admin-users-page", "property": "data"},
            "inputs": [
                {"id": "admin-users-previous", "property": "n_clicks", "value": 0},
                {"id": "admin-users-next", "property": "n_clicks", "value": 1},
            ],
            "state": [{"id": "admin-users-page", "property": "data", "value": 1}],
            "changedPropIds": ["admin-users-next.n_clicks"],
        }
        self.assertEqual(
            self.client.post(
                "/_dash-update-component", json=body, headers=csrf_headers(self.client)
            ).status_code,
            403,
        )

    def test_retired_workspaces_are_not_mutation_surfaces(self):
        self.sync()
        for path in (
            "/workspace/admin",
            "/workspace/admin/create",
            "/workspace/admin/members",
            "/auth/registration",
        ):
            self.assertEqual(self.client.get(path).status_code, 410)
        self.assertEqual(
            self.client.post(
                "/auth/workspace", json={}, headers=csrf_headers(self.client)
            ).status_code,
            410,
        )
        self.client.get("/_dash-layout")
        self.assertFalse(
            any(
                "workspace-admin" in key
                or "workspace-members" in key
                or "workspace-create" in key
                for key in app.callback_map
            )
        )

    def test_signup_recovery_visibility_and_logout(self):
        signup = self.client.get("/signup").get_data(as_text=True)
        self.assertNotIn('data-provider="google"', signup)
        self.assertIn('data-password-toggle="auth-password"', signup)
        recovery = self.client.get("/auth/recovery?step=update").get_data(as_text=True)
        self.assertIn("Confirm New Password", recovery)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        self.sync()
        self.assertEqual(
            self.client.delete(
                "/auth/session", headers=csrf_headers(self.client)
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/_dash-dependencies").status_code, 401)

    def test_configuration_and_origin_fail_closed(self):
        with patch.dict(app.server.config, SUPABASE_PUBLIC_KEY=""):
            self.assertEqual(self.sync().status_code, 503)
        self.assertEqual(
            self.client.post(
                "/auth/session",
                json={"access_token": token()},
                headers={"Origin": "https://evil.test"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/auth/password",
                json={"email": "x@example.test", "password": "x"},
                headers={"Origin": "http://localhost"},
            ).status_code,
            403,
        )

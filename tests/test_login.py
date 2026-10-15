"""Offline authentication/membership protection; no external accounts or queries."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from auth_fixtures import csrf_headers, CONFIG, FakeGateway, WORKSPACE


class LoginTests(unittest.TestCase):
    def setUp(self):
        app.server.extensions["auth_limiter"].reset()
        self.client = app.server.test_client()
        FakeGateway.calls = []
        for mapping, values in (
            (app.server.config, CONFIG),
            (app.server.extensions, {"supabase_gateway_factory": FakeGateway}),
        ):
            item = patch.dict(mapping, values)
            item.start()
            self.addCleanup(item.stop)

    def sync(self, token="approved", next="/workspace"):
        return self.client.post(
            "/auth/session",
            json={"access_token": token, "next": next},
            headers=csrf_headers(self.client),
        )

    def test_revoked_sign_in_reports_revocation_and_clears_cookie(self):
        self.sync()
        response = self.sync(token="revoked")
        self.assertFalse(response.json["approved"])
        self.assertEqual(response.json["requestStatus"], "revoked")
        self.assertIn("Max-Age=0", response.headers.get("Set-Cookie", ""))
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_public_auth_pages_and_safe_redirect(self):
        for route in (
            "/login",
            "/signup",
            "/auth/callback",
            "/auth/recovery",
            "/auth/access-pending",
            "/auth/config",
        ):
            self.assertEqual(self.client.get(route).status_code, 200)
        self.assertEqual(
            self.sync(next="//attacker.example").json["next"], "/dashboard"
        )
        config = self.client.get("/auth/config").json
        self.assertEqual(set(config), {"url", "publicKey", "providers"})
        self.assertNotIn("SECRET", str(config))

    def test_registration_target_is_public_but_bounded_and_not_access(self):
        response = self.client.get("/auth/registration?workspace=" + "a" * 48)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json), {"code", "name"})
        self.assertNotIn("aw_access", response.headers.get("Set-Cookie", ""))
        self.assertEqual(
            self.client.get("/auth/registration?workspace=forged").status_code, 400
        )
        self.assertFalse(
            any(name == "claim_workspace_approvals" for name, _ in FakeGateway.calls)
        )

    def test_unapproved_sync_reports_request_status_without_claiming(self):
        response = self.sync("no-member")
        self.assertFalse(response.json["approved"])
        self.assertEqual(response.json["requestStatus"], "pending")
        self.assertFalse(
            any(name == "claim_workspace_approvals" for name, _ in FakeGateway.calls)
        )

    def test_signup_is_email_only_and_login_offers_social_sign_in(self):
        signup = self.client.get("/signup").get_data(as_text=True)
        self.assertNotIn('data-provider="google"', signup)
        self.assertNotIn('data-provider="github"', signup)
        self.assertNotIn("Sign up with email →", signup)
        login = self.client.get("/login").get_data(as_text=True)
        self.assertIn('data-provider="google"', login)

    def test_recovery_forms_are_public_and_do_not_grant_access(self):
        request_form = self.client.get("/auth/recovery")
        self.assertIn("Send Reset Link", request_form.get_data(as_text=True))
        update_form = self.client.get("/auth/recovery?step=update")
        html = update_form.get_data(as_text=True)
        self.assertIn("Confirm New Password", html)
        self.assertIn("Update Password", html)
        self.assertIn("Request a New Reset Link", html)
        self.assertNotIn("aw_access", update_form.headers.get("Set-Cookie", ""))
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_session_cookie_and_verified_workspace_summary(self):
        response = self.sync()
        cookie = response.headers.getlist("Set-Cookie")
        self.assertTrue(
            any(
                "aw_access=" in item and "HttpOnly" in item and "SameSite=Lax" in item
                for item in cookie
            )
        )
        self.assertEqual(self.client.get("/workspace").status_code, 200)
        self.client.get("/_dash-layout")
        response = self.client.post(
            "/_dash-update-component",
            json={
                "output": "workspace-summary-details.children",
                "outputs": {"id": "workspace-summary-details", "property": "children"},
                "inputs": [
                    {
                        "id": "app-location",
                        "property": "pathname",
                        "value": "/workspace",
                    }
                ],
                "state": [],
                "changedPropIds": ["app-location.pathname"],
            },
            headers=csrf_headers(self.client),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("owner@example.test", response.get_data(as_text=True))
        self.assertNotIn("access_token", response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {"workspace_id": WORKSPACE["id"]})

    def test_invalid_unconfirmed_unapproved_and_outage(self):
        for token, expected in (
            ("expired", 401),
            ("tampered", 401),
            ("unconfirmed", 403),
            ("outage", 503),
        ):
            self.assertEqual(self.sync(token).status_code, expected)
        result = self.sync("no-member")
        self.assertEqual(result.json["approved"], False)
        self.assertEqual(result.json["next"], "/auth/access-pending")
        self.assertIsNone(self.client.get_cookie("aw_access"))
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        self.assertEqual(
            self.client.get("/dashboard", headers={"Accept": "text/html"}).location,
            "/login?next=%2Fdashboard",
        )

    def test_mutations_require_exact_origin_and_no_token_fallback(self):
        self.assertEqual(
            self.client.post(
                "/auth/session",
                json={"access_token": "approved"},
                headers={"Origin": "https://evil.test"},
            ).status_code,
            403,
        )
        self.sync()
        self.assertEqual(
            self.client.post(
                "/auth/session", json={}, headers=csrf_headers(self.client)
            ).status_code,
            401,
        )
        self.assertEqual(self.client.delete("/auth/session").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/auth/workspace",
                json={"workspace_id": "forged"},
                headers=csrf_headers(self.client),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/auth/workspace",
                json={"workspace_id": WORKSPACE["id"]},
                headers=csrf_headers(self.client),
            ).status_code,
            200,
        )

    def test_pending_sign_in_clears_previously_approved_app_session(self):
        self.sync()
        self.assertIsNotNone(self.client.get_cookie("aw_access"))
        result = self.sync("no-member")
        self.assertFalse(result.json["approved"])
        self.assertIsNone(self.client.get_cookie("aw_access"))
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {})
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_revocation_is_checked_on_every_request_and_logout(self):
        self.sync()
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        self.client.set_cookie("aw_access", "no-member")
        self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
        self.client.set_cookie("aw_access", "expired")
        self.assertEqual(self.client.get("/_dash-dependencies").status_code, 401)
        self.sync()
        self.assertEqual(
            self.client.delete(
                "/auth/session", headers=csrf_headers(self.client)
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_viewer_cannot_admin_and_basic_auth_is_removed(self):
        self.sync("viewer")
        self.assertEqual(self.client.get("/workspace/admin").status_code, 403)
        anonymous = app.server.test_client()
        self.assertEqual(
            anonymous.get(
                "/_dash-layout", headers={"Authorization": "Basic dXNlcjpwYXNz"}
            ).status_code,
            401,
        )
        self.assertEqual(
            anonymous.get("/workspace", headers={"Accept": "text/html"}).status_code,
            302,
        )

    def test_configuration_errors_fail_closed_and_secure_cookie(self):
        with patch.dict(app.server.config, AUTH_APP_ORIGIN="http://example.com"):
            self.assertEqual(self.client.get("/auth/config").status_code, 503)
        with patch.dict(app.server.config, SUPABASE_PUBLIC_KEY=""):
            self.assertEqual(self.sync().status_code, 503)
        with patch.dict(app.server.config, SESSION_COOKIE_SECURE=True):
            self.assertTrue(
                any(
                    "Secure" in c
                    for c in self.sync().headers.getlist("Set-Cookie")
                    if "aw_access" in c
                )
            )

    def test_forged_admin_callback_cannot_bypass_role(self):
        self.sync("viewer")
        self.client.get("/_dash-layout")
        key = next(
            k
            for k, item in app.callback_map.items()
            if "workspace-members-edit-status.children" in k
            and item["inputs"][0]["id"] == "workspace-members-save"
        )
        FakeGateway.calls = []
        response = self.client.post(
            "/_dash-update-component",
            json={
                "output": key,
                "outputs": [
                    output.to_dict() for output in app.callback_map[key]["output"]
                ],
                "inputs": [
                    {"id": "workspace-members-save", "property": "n_clicks", "value": 1}
                ],
                "state": [
                    {
                        "id": "workspace-members-target",
                        "property": "data",
                        "value": {
                            "workspace_id": WORKSPACE["id"],
                            "user_id": "44444444-4444-4444-4444-444444444444",
                        },
                    },
                    {
                        "id": "workspace-members-edit-role",
                        "property": "value",
                        "value": "owner",
                    },
                    {
                        "id": "workspace-members-edit-active",
                        "property": "value",
                        "value": "active",
                    },
                    {
                        "id": "workspace-members-scope",
                        "property": "value",
                        "value": WORKSPACE["id"],
                    },
                ],
                "changedPropIds": ["workspace-members-save.n_clicks"],
            },
            headers=csrf_headers(self.client),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            any(name == "change_workspace_member" for name, _ in FakeGateway.calls)
        )

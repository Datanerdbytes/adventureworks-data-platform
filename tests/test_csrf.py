"""Offline CSRF tests at real Flask/Dash request boundaries."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app, serve_layout
from auth import CSRF_COOKIE, csrf_signer, valid_csrf_token
from auth_fixtures import CONFIG, FakeGateway, csrf_headers, token as fixture_token


class CsrfTests(unittest.TestCase):
    def setUp(self):
        app.server.extensions["auth_limiter"].reset()
        for mapping, values in (
            (app.server.config, CONFIG),
            (app.server.extensions, {"supabase_gateway_factory": FakeGateway}),
        ):
            item = patch.dict(mapping, values)
            item.start()
            self.addCleanup(item.stop)
        self.client = app.server.test_client()
        FakeGateway.calls = []

    def sync(self, client=None, token="approved"):
        client = client or self.client
        return client.post(
            "/auth/session",
            json={"access_token": fixture_token(token)},
            headers=csrf_headers(client),
        )

    def test_issuance_is_private_and_origin_bounded(self):
        for headers in (
            {},
            {"X-CSRF-Request": "1", "Origin": "https://foreign.test"},
            {"X-CSRF-Request": "1", "Sec-Fetch-Site": "cross-site"},
        ):
            response = self.client.get("/auth/csrf", headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertIsNone(self.client.get_cookie(CSRF_COOKIE))
        response = self.client.get("/auth/csrf", headers={"X-CSRF-Request": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["csrfToken"]), 64)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        self.assertNotIn("Max-Age", response.headers["Set-Cookie"])
        self.assertEqual(
            set(self.client.get("/auth/config").json),
            {"url", "publicKey", "providers", "passwordLockoutEnabled"},
        )
        with patch.dict(app.server.config, SESSION_COOKIE_SECURE=True):
            other = app.server.test_client()
            issued = other.get("/auth/csrf", headers={"X-CSRF-Request": "1"})
            self.assertIn("Secure", issued.headers["Set-Cookie"])

    def test_invalid_pre_session_tokens_have_no_external_side_effects(self):
        valid = csrf_headers(self.client)
        other = app.server.test_client()
        wrong_session = csrf_headers(other)["X-CSRF-Token"]
        for token in (None, "", "bad", "a" * 65, "é" * 64, wrong_session):
            headers = {"Origin": "http://localhost"}
            if token is not None:
                headers["X-CSRF-Token"] = token
            for method in ("POST", "DELETE"):
                FakeGateway.calls = []
                with patch.object(
                    FakeGateway,
                    "user",
                    side_effect=AssertionError("must not validate identity"),
                ):
                    response = self.client.open(
                        "/auth/session",
                        method=method,
                        json={"access_token": fixture_token()},
                        headers=headers,
                    )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(FakeGateway.calls, [])
        self.assertEqual(
            self.client.post(
                "/auth/session", json={"access_token": fixture_token()}, headers=valid
            ).status_code,
            200,
        )

    def test_cookie_forgery_expiry_and_auth_context_binding(self):
        before_login = csrf_headers(self.client)
        self.assertEqual(self.sync().status_code, 200)
        self.assertEqual(
            self.client.post(
                "/auth/session",
                json={"access_token": fixture_token()},
                headers=before_login,
            ).status_code,
            403,
        )
        current = csrf_headers(self.client)
        self.client.set_cookie("aw_access", "refreshed-access")
        self.assertEqual(
            self.client.post("/auth/session", json={}, headers=current).status_code,
            403,
        )
        current = csrf_headers(self.client)
        self.assertEqual(
            self.client.post(
                "/auth/session",
                json={"access_token": fixture_token()},
                headers=current,
            ).status_code,
            200,
        )
        for value in ("forged-cookie", "é" * 64):
            self.client.set_cookie(CSRF_COOKIE, value)
            self.assertEqual(
                self.client.post("/auth/session", json={}, headers=current).status_code,
                403,
            )
        with app.server.test_request_context():
            with patch("itsdangerous.timed.time.time", return_value=1):
                expired = csrf_signer().dumps("a" * 64)
        self.client.set_cookie(CSRF_COOKIE, expired)
        self.assertEqual(
            self.client.post("/auth/session", json={}, headers=current).status_code,
            403,
        )
        renewed = csrf_headers(self.client)
        self.assertNotEqual(renewed["X-CSRF-Token"], current["X-CSRF-Token"])
        with app.server.test_request_context():
            for malformed in (None, [], {}, 42, "é" * 64):
                self.assertFalse(valid_csrf_token(malformed))

    def test_refresh_tabs_logout_and_pending_signin(self):
        self.sync()
        first = csrf_headers(self.client)
        second_tab = csrf_headers(self.client)
        self.assertEqual(first, second_tab)
        self.sync()  # identical identity/access cookie doesn't invalidate token
        self.assertEqual(first, csrf_headers(self.client))
        response = self.client.delete("/auth/session", headers=first)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.get_cookie(CSRF_COOKIE))
        self.assertEqual(
            self.client.delete("/auth/session", headers=first).status_code, 403
        )
        self.assertNotEqual(first, csrf_headers(self.client))
        self.sync()
        self.assertTrue(self.sync(token="no-member").json["approved"])
        self.assertIsNotNone(self.client.get_cookie("aw_access"))

    def test_actual_dash_mutation_rejects_before_admin_service(self):
        self.sync()
        self.client.get("/_dash-layout")
        key = next(key for key in app.callback_map if "admin-users-page.data" == key)
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
        valid = csrf_headers(self.client)
        for headers in (
            {"Origin": "http://localhost"},
            {**valid, "Origin": "https://foreign.test"},
        ):
            with patch("user_admin._service_request") as remote:
                self.assertEqual(
                    self.client.post(
                        "/_dash-update-component", json=body, headers=headers
                    ).status_code,
                    403,
                )
                remote.assert_not_called()
        allowed = self.client.post("/_dash-update-component", json=body, headers=valid)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json["response"]["admin-users-page"]["data"], 2)

    def test_selected_workspace_is_only_flask_session_state_and_layout_is_context_free(
        self,
    ):
        self.sync()
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {})
        self.assertIsNotNone(serve_layout())
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn("{{ session", html)
        self.assertNotIn(csrf_headers(self.client)["X-CSRF-Token"], html)

    def test_issuer_quota_is_independent_and_read_gets_remain_available(self):
        last = None
        for _ in range(600):
            last = self.client.get("/auth/csrf", headers={"X-CSRF-Request": "1"})
            self.assertEqual(last.status_code, 200)
        limited = self.client.get("/auth/csrf", headers={"X-CSRF-Request": "1"})
        self.assertEqual(limited.status_code, 429)
        self.assertTrue(limited.is_json)
        self.assertEqual(limited.headers["Cache-Control"], "private, no-store")
        self.assertEqual(self.client.get("/auth/config").status_code, 200)
        response = self.client.post(
            "/auth/session",
            json={"access_token": fixture_token()},
            headers={
                "Origin": "http://localhost",
                "X-CSRF-Token": last.json["csrfToken"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)

    def test_rejected_origin_or_csrf_cannot_clear_an_existing_access_cookie(self):
        self.sync()
        cookie = self.client.get_cookie("aw_access").value
        valid = csrf_headers(self.client)
        for headers in (
            {"Origin": "http://localhost"},
            {**valid, "Origin": "https://foreign.test"},
        ):
            for method in ("POST", "DELETE"):
                response = self.client.open(
                    "/auth/session", method=method, json={}, headers=headers
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.client.get_cookie("aw_access").value, cookie)
                self.assertNotIn(
                    "aw_access=", str(response.headers.getlist("Set-Cookie"))
                )

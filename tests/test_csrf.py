"""Offline CSRF tests at real Flask/Dash request boundaries."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app, serve_layout
from auth import CSRF_COOKIE, csrf_signer, valid_csrf_token
from auth_fixtures import CONFIG, FakeGateway, WORKSPACE, csrf_headers
from pages.workspace_admin import ACTION_INPUTS, STATE_FIELDS


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
            "/auth/session", json={"access_token": token}, headers=csrf_headers(client)
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
            set(self.client.get("/auth/config").json), {"url", "publicKey", "providers"}
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
                        json={"access_token": "approved"},
                        headers=headers,
                    )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(FakeGateway.calls, [])
        self.assertEqual(
            self.client.post(
                "/auth/session", json={"access_token": "approved"}, headers=valid
            ).status_code,
            200,
        )

    def test_cookie_forgery_expiry_and_auth_context_binding(self):
        before_login = csrf_headers(self.client)
        self.assertEqual(self.sync().status_code, 200)
        self.assertEqual(
            self.client.post(
                "/auth/workspace",
                json={"workspace_id": WORKSPACE["id"]},
                headers=before_login,
            ).status_code,
            403,
        )
        current = csrf_headers(self.client)
        self.client.set_cookie("aw_access", "refreshed-access")
        self.assertEqual(
            self.client.post("/auth/workspace", json={}, headers=current).status_code,
            403,
        )
        current = csrf_headers(self.client)
        self.assertEqual(
            self.client.post(
                "/auth/workspace",
                json={"workspace_id": WORKSPACE["id"]},
                headers=current,
            ).status_code,
            200,
        )
        for value in ("forged-cookie", "é" * 64):
            self.client.set_cookie(CSRF_COOKIE, value)
            self.assertEqual(
                self.client.post(
                    "/auth/workspace", json={}, headers=current
                ).status_code,
                403,
            )
        with app.server.test_request_context():
            with patch("itsdangerous.timed.time.time", return_value=1):
                expired = csrf_signer().dumps("a" * 64)
        self.client.set_cookie(CSRF_COOKIE, expired)
        self.assertEqual(
            self.client.post("/auth/workspace", json={}, headers=current).status_code,
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
        self.assertFalse(self.sync(token="no-member").json["approved"])
        self.assertIsNone(self.client.get_cookie(CSRF_COOKIE))
        self.assertIsNone(self.client.get_cookie("aw_access"))

    def mutation_body(self, action="save"):
        self.client.get("/_dash-layout")
        if action == "change":
            key = next(
                key
                for key, item in app.callback_map.items()
                if "workspace-members-edit-status.children" in key
                and item["inputs"][0]["id"] == "workspace-members-save"
            )
            return {
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
                        "value": "viewer",
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
            }
        if action == "create":
            key = next(
                key
                for key in app.callback_map
                if "workspace-create-status.children" in key
            )
            return {
                "output": key,
                "outputs": [
                    output.to_dict() for output in app.callback_map[key]["output"]
                ],
                "inputs": [
                    {"id": "workspace-create-form", "property": "n_submit", "value": 1}
                ],
                "state": [
                    {
                        "id": "workspace-create-" + name,
                        "property": "value",
                        "value": value,
                    }
                    for name, value in zip(
                        ("name", "team", "purpose", "owner"),
                        (
                            "New workspace",
                            "Analytics",
                            "Reporting",
                            "owner@example.test",
                        ),
                    )
                ],
                "changedPropIds": ["workspace-create-form.n_submit"],
            }
        key = next(
            key
            for key, item in app.callback_map.items()
            if "workspace-admin-status.children" in key
            and item["inputs"][0]["id"] == "workspace-admin-save"
        )
        return {
            "output": key,
            "outputs": [
                {"id": "workspace-admin-status", "property": "children"},
                {"id": "workspace-admin-reload", "property": "href"},
            ],
            "inputs": [
                {
                    "id": "workspace-admin-" + name,
                    "property": "n_clicks",
                    "value": int(name == action),
                }
                for name in ACTION_INPUTS
            ],
            "state": [
                {
                    "id": "workspace-admin-" + name,
                    "property": "value",
                    "value": {
                        "member": "member-id",
                        "member-role": "viewer",
                        "member-active": "active",
                    }.get(name, "Example"),
                }
                for name in STATE_FIELDS
            ],
            "changedPropIds": ["workspace-admin-" + action + ".n_clicks"],
        }

    def test_actual_dash_mutation_rejects_before_rpc_and_allows_valid_token(self):
        self.sync()
        for action, rpc in (
            ("save", "update_workspace"),
            ("change", "change_workspace_member"),
        ):
            body = self.mutation_body(action)
            valid = csrf_headers(self.client)
            foreign_session = csrf_headers(app.server.test_client())["X-CSRF-Token"]
            for headers in (
                {"Origin": "http://localhost"},
                {**valid, "X-CSRF-Token": "a" * 64},
                {**valid, "X-CSRF-Token": foreign_session},
                {**valid, "Origin": "https://foreign.test"},
            ):
                FakeGateway.calls = []
                response = self.client.post(
                    "/_dash-update-component", json=body, headers=headers
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(FakeGateway.calls, [])
            FakeGateway.calls = []
            response = self.client.post(
                "/_dash-update-component", json=body, headers=valid
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(any(name == rpc for name, _ in FakeGateway.calls))

    def test_selected_workspace_is_only_flask_session_state_and_layout_is_context_free(
        self,
    ):
        self.sync()
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {"workspace_id": WORKSPACE["id"]})
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
            json={"access_token": "approved"},
            headers={
                "Origin": "http://localhost",
                "X-CSRF-Token": last.json["csrfToken"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)

    def test_creation_and_approval_callback_csrf_boundaries(self):
        self.sync(token="platform")
        create = self.mutation_body("create")
        review_key = next(
            key
            for key, item in app.callback_map.items()
            if "workspace-admin-status.children" in key
            and item["inputs"][0]["id"] == "workspace-admin-requests"
        )
        review = {
            "output": review_key,
            "outputs": [
                {"id": "workspace-admin-status", "property": "children"},
                {"id": "workspace-admin-reload", "property": "href"},
            ],
            "inputs": [
                {
                    "id": "workspace-admin-requests",
                    "property": "cellRendererData",
                    "value": {
                        "value": {
                            "request_id": "request-id",
                            "decision": "approved",
                            "role": "viewer",
                            "reason": "",
                        }
                    },
                }
            ],
            "state": [],
            "changedPropIds": ["workspace-admin-requests.cellRendererData"],
        }
        for body, rpc in (
            (create, "create_workspace"),
            (review, "review_workspace_request"),
        ):
            self.sync(token="platform")
            FakeGateway.calls = []
            rejected = self.client.post(
                "/_dash-update-component",
                json=body,
                headers={"Origin": "http://localhost"},
            )
            self.assertEqual(rejected.status_code, 403)
            self.assertEqual(FakeGateway.calls, [])
            allowed = self.client.post(
                "/_dash-update-component", json=body, headers=csrf_headers(self.client)
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertTrue(any(name == rpc for name, _ in FakeGateway.calls))
            if rpc == "create_workspace":
                self.sync(token="approved")
                FakeGateway.calls = []
                forbidden = self.client.post(
                    "/_dash-update-component",
                    json=body,
                    headers=csrf_headers(self.client),
                )
                self.assertEqual(forbidden.status_code, 403)
                self.assertFalse(any(name == rpc for name, _ in FakeGateway.calls))

"""Embedded-browser login keeps the dashboard and callbacks protected."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict(
            app.server.config,
            DASH_AUTH_USERNAME="login-test",
            DASH_AUTH_PASSWORD="test-password",
        )
        self.config.start()
        self.addCleanup(self.config.stop)
        self.client = app.server.test_client()

    def sign_in(
        self,
        password="test-password",
        origin="http://localhost",
        destination="/dashboard/executive",
    ):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            csrf = session["login_csrf"]
        return self.client.post(
            "/login",
            data={
                "username": "login-test",
                "password": password,
                "csrf": csrf,
                "next": destination,
            },
            headers={"Origin": origin},
        )

    def test_page_redirect_and_api_protection(self):
        response = self.client.get(
            "/dashboard/executive", headers={"Accept": "text/html"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?", response.location)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_login_session_and_credentials_rotation(self):
        response = self.sign_in()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, "/dashboard/executive")
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", response.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        with self.client.session_transaction() as session:
            self.assertNotIn("test-password", str(dict(session)))
        with patch.dict(app.server.config, DASH_AUTH_PASSWORD="rotated"):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_invalid_password_origin_csrf_and_redirect(self):
        self.assertEqual(self.sign_in(password="wrong").status_code, 401)
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        self.assertEqual(
            self.sign_in(origin="https://attacker.example").status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/login",
                data={"username": "login-test", "password": "test-password"},
                headers={"Origin": "http://localhost"},
            ).status_code,
            403,
        )
        response = self.sign_in(destination="//attacker.example")
        self.assertEqual(response.location, "/dashboard")

    def test_expired_or_tampered_session_cannot_authorize(self):
        self.sign_in()
        with self.client.session_transaction() as session:
            session["credential_version"] = "invalid"
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        self.client.set_cookie("session", "tampered")
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)

    def test_workspace_redirect_stays_protected(self):
        response = self.client.get("/workspace", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=%2Fworkspace", response.location)
        signed_in = self.sign_in(destination="/workspace")
        self.assertEqual(signed_in.location, "/workspace")
        self.assertEqual(self.client.get("/workspace").status_code, 200)

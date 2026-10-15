"""REST error handling and administration callbacks are tested without services."""

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError
from werkzeug.exceptions import Forbidden

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from governance import SupabaseGateway, GovernanceError
from auth import auth_configuration_error, install_auth
from auth_fixtures import CONFIG, WORKSPACE
from app import app
from flask import Flask, g
from pages import workspace_admin


class GovernanceTests(unittest.TestCase):
    def test_publishable_key_name_and_legacy_fallback(self):
        for values, expected in (
            ({"NEXT_PUBLIC_SUPABASE_ANON_KEY": "legacy-public"}, "legacy-public"),
            (
                {
                    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": "new-public",
                    "NEXT_PUBLIC_SUPABASE_ANON_KEY": "legacy-public",
                },
                "new-public",
            ),
        ):
            with (
                patch.dict(
                    "os.environ",
                    {**values, "RATE_LIMIT_ENVIRONMENT": "testing"},
                    clear=True,
                ),
                patch("auth.load_dotenv"),
            ):
                server = Flask("key-name-test")
                install_auth(server)
                self.assertEqual(server.config["SUPABASE_PUBLIC_KEY"], expected)

    def test_privileged_public_keys_rejected(self):
        self.assertIsNotNone(
            auth_configuration_error(
                {**CONFIG, "SUPABASE_PUBLIC_KEY": "sb_secret_private"}
            )
        )
        self.assertIsNone(auth_configuration_error(CONFIG))

    def test_provider_errors_are_sanitized_and_fail_closed(self):
        client = SupabaseGateway("https://project.supabase.co", "public", "access")
        for error, status in [
            (URLError("secret connection URL"), 503),
            (HTTPError("url", 401, "secret", {}, io.BytesIO(b"{}")), 401),
        ]:
            with (
                patch("governance.urlopen", side_effect=error),
                self.assertRaises(GovernanceError) as caught,
            ):
                client.user()
            self.assertEqual(caught.exception.status, status)
            self.assertNotIn("secret", str(caught.exception))
        error = HTTPError(
            "url", 400, "secret", {}, io.BytesIO(b'{"code":"42501","message":"secret"}')
        )
        with (
            patch("governance.urlopen", side_effect=error),
            self.assertRaises(GovernanceError) as caught,
        ):
            client.rpc("change_workspace_member")
        self.assertEqual(caught.exception.status, 403)

        error = HTTPError("url", 503, "secret", {}, io.BytesIO(b"[]"))
        with (
            patch("governance.urlopen", side_effect=error),
            self.assertRaises(GovernanceError) as caught,
        ):
            client.rpc("workspace_context")
        self.assertEqual(caught.exception.status, 503)

    def test_provider_requires_confirmed_identity(self):
        client = SupabaseGateway("https://project.supabase.co", "public", "access")
        for user in (
            {},
            {"id": "id", "email": "email"},
            {"id": "id", "email": "email", "user_metadata": {"role": "owner"}},
        ):
            with (
                patch.object(client, "request", return_value=user),
                self.assertRaises(GovernanceError),
            ):
                client.user()

    def test_revoked_membership_lookup_is_bounded_and_fails_closed(self):
        client = SupabaseGateway("https://project.supabase.co", "public", "token")
        with patch.object(
            client, "request", return_value=[{"workspace_id": "test"}]
        ) as lookup:
            self.assertTrue(client.has_revoked_membership("user-id"))
            self.assertIn("user_id=eq.user-id", lookup.call_args.args[0])
            self.assertIn("active=eq.false&limit=1", lookup.call_args.args[0])
        with patch.object(client, "request", return_value=[]):
            self.assertFalse(client.has_revoked_membership("user-id"))
        with patch.object(client, "request", return_value=None):
            with self.assertRaises(GovernanceError):
                client.has_revoked_membership("user-id")

    def test_admin_ui_role_gating_and_no_import_queries(self):
        with app.server.test_request_context():
            g.workspace = {**WORKSPACE, "role": "viewer"}
            g.governance = Mock()
            with self.assertRaises(Forbidden):
                workspace_admin.populate("/workspace/admin", 0)
            g.governance.rpc.assert_not_called()
            g.workspace = {**WORKSPACE, "role": "admin"}
            g.workspace_context = {"platform_admin": False}
            g.governance.rpc.return_value = {
                "members": [],
                "approvals": [],
                "events": [],
                "member_count": 0,
                "approval_count": 0,
            }
            rendered = workspace_admin.populate("/workspace/admin", 0)
            self.assertNotIn("Create Workspace", str(rendered))
            self.assertNotIn("Save Details", str(rendered))
            self.assertIn("Awaiting Approval", str(rendered))

    def test_owner_details_are_read_only_until_editor_opens(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": False}
            g.governance = Mock()
            g.governance.rpc.return_value = {
                "members": [],
                "approvals": [],
                "events": [],
                "member_count": 0,
                "approval_count": 0,
            }
            rendered = str(workspace_admin.populate("/workspace/admin", 0))
            self.assertIn("Edit Details", rendered)
            self.assertIn("is_open=False", rendered)
            self.assertIn("admin-workspace-details", rendered)
            self.assertNotIn("Starting Record", rendered)

    def test_workspace_editor_is_owner_only_and_cancel_does_not_write(self):
        with app.server.test_request_context():
            g.workspace = {**WORKSPACE, "role": "admin"}
            g.governance = Mock()
            with self.assertRaises(Forbidden):
                workspace_admin.toggle_details_editor(1, 0)
            g.workspace = WORKSPACE
            with patch.object(
                workspace_admin, "ctx", Mock(triggered_id="workspace-admin-edit")
            ):
                self.assertTrue(workspace_admin.toggle_details_editor(1, 0))
            with patch.object(
                workspace_admin, "ctx", Mock(triggered_id="workspace-admin-edit-cancel")
            ):
                self.assertFalse(workspace_admin.toggle_details_editor(1, 1))
            g.governance.rpc.assert_not_called()

    def test_request_row_decisions_require_admin_and_validate_roles(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": False}
            g.governance = Mock()
            for decision in ("approved", "rejected"):
                event = {
                    "value": {
                        "request_id": "request-id",
                        "role": "viewer",
                        "decision": decision,
                    }
                }
                _, destination = workspace_admin.review_request_row(event)
                self.assertEqual(destination, "/workspace/admin")
                g.governance.rpc.assert_called_with(
                    "review_workspace_request",
                    p_workspace=WORKSPACE["id"],
                    p_request="request-id",
                    p_decision=decision,
                    p_role="viewer",
                    p_reason="",
                )
            g.workspace = {**WORKSPACE, "role": "viewer"}
            with self.assertRaises(GovernanceError):
                workspace_admin.review_request_row(event)
            with self.assertRaises(GovernanceError):
                workspace_admin.search_access_requests("person@example.com")
            g.workspace = {**WORKSPACE, "role": "admin"}
            g.governance.rpc.reset_mock()
            event["value"]["role"] = "owner"
            with self.assertRaises(Forbidden):
                workspace_admin.review_request_row(event)
            g.governance.rpc.assert_not_called()
            event["value"]["role"] = "viewer"
            event["value"]["decision"] = "forged"
            workspace_admin.review_request_row(event)
            g.governance.rpc.assert_not_called()

    def test_administration_renders_with_workspace_registration_qr(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": True}
            g.governance = Mock()
            g.governance.rpc.return_value = {
                "members": [],
                "approvals": [],
                "events": [],
                "member_count": 1,
                "approval_count": 0,
                "registration_code": "a" * 48,
            }
            rendered = str(workspace_admin.populate("/workspace/admin", 0))
            self.assertIn("data:image/svg+xml", rendered)
            self.assertIn("workspace-admin-registration-copy", rendered)
            self.assertIn("/signup?workspace=" + "a" * 48, rendered)
            self.assertNotIn("workspace-admin-registration-link", rendered)
            self.assertLess(
                rendered.index("Workspace Registration"),
                rendered.index("CURRENT WORKSPACE"),
            )
            self.assertIn("Awaiting Approval", rendered)
            self.assertIn("WorkspaceRequestDecision", rendered)
            self.assertIn("WorkspaceRequestRole", rendered)
            self.assertIn("'label': 'Viewer', 'value': 'viewer'", rendered)
            self.assertIn("'label': 'Owner', 'value': 'owner'", rendered)
            self.assertNotIn("Approve Selected", rendered)
            self.assertNotIn("Approve an Email", rendered)
            self.assertNotIn("workspace-admin-approve", rendered)
            self.assertIn("Edit Details", rendered)

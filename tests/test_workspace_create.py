"""Offline tests for the dedicated workspace creation flow."""

import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from flask import g, session
from werkzeug.exceptions import Forbidden

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from auth_fixtures import WORKSPACE, CONFIG, FakeGateway, csrf_headers
from governance import GovernanceError
from pages import workspace_create, workspace_admin


class WorkspaceCreateTests(unittest.TestCase):
    def test_layout_has_no_requests_and_form_requires_platform_access(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": False}
            g.governance = Mock()
            workspace_create.layout()
            with self.assertRaises(Forbidden):
                workspace_create.populate(workspace_create.PATH)
            with self.assertRaises(Forbidden):
                workspace_create.create_workspace(
                    1, "Example", "Team", "", "a@example.test"
                )
            g.governance.rpc.assert_not_called()
            g.workspace_context = {"platform_admin": True}
            workspace_create.populate(workspace_create.PATH)
            g.governance.rpc.assert_not_called()

    def test_invalid_fields_do_not_create_or_change_workspace(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": True}
            g.governance = Mock()
            session["workspace_id"] = WORKSPACE["id"]
            result = workspace_create.create_workspace(
                1, "  ", "T" * 121, "P" * 1001, "invalid"
            )
            self.assertEqual(result[2:6], (True, True, True, True))
            g.governance.rpc.assert_not_called()
            self.assertEqual(session["workspace_id"], WORKSPACE["id"])

    def test_success_uses_existing_rpc_and_switches_workspace(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": True}
            g.governance = Mock()
            g.governance.rpc.return_value = "new-workspace-id"
            result = workspace_create.create_workspace(
                1, " New workspace ", " Team ", None, " owner@example.test "
            )
            g.governance.rpc.assert_called_once_with(
                "create_workspace",
                p_name="New workspace",
                p_team="Team",
                p_purpose="",
                p_owner_email="owner@example.test",
            )
            self.assertEqual(result[1], "/workspace/admin")
            self.assertEqual(dict(session), {"workspace_id": "new-workspace-id"})

    def test_owner_rejection_retains_current_workspace_and_form_values(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": True}
            g.governance = Mock()
            g.governance.rpc.side_effect = GovernanceError(
                "Initial owner must have a confirmed account", 400
            )
            session["workspace_id"] = WORKSPACE["id"]
            result = workspace_create.create_workspace(
                1, "Example", "Team", "", "unknown@example.test"
            )
            self.assertIn("confirmed account", str(result[0]))
            self.assertEqual(session["workspace_id"], WORKSPACE["id"])
            self.assertIs(result[1], workspace_create.dash.no_update)

    def test_direct_route_requires_platform_admin(self):
        with (
            patch.dict(app.server.config, CONFIG),
            patch.dict(
                app.server.extensions, {"supabase_gateway_factory": FakeGateway}
            ),
        ):
            app.server.extensions["auth_limiter"].reset()
            client = app.server.test_client()
            self.assertEqual(client.get(workspace_create.PATH).status_code, 401)
            for token, status in (
                ("approved", 403),
                ("viewer", 403),
                ("platform", 200),
            ):
                client.post(
                    "/auth/session",
                    json={"access_token": token},
                    headers=csrf_headers(client),
                )
                self.assertEqual(client.get(workspace_create.PATH).status_code, status)

    def test_admin_page_links_to_creation_without_embedded_form(self):
        with app.server.test_request_context():
            g.workspace = WORKSPACE
            g.workspace_context = {"platform_admin": True}
            g.governance = Mock()
            g.governance.rpc.return_value = dict(
                members=[], approvals=[], events=[], member_count=0, approval_count=0
            )
            rendered = str(workspace_admin.populate("/workspace/admin", 0))
            self.assertIn(workspace_create.PATH, rendered)
            self.assertNotIn("workspace-admin-new-name", rendered)
            g.workspace_context = {"platform_admin": False}
            self.assertNotIn(
                workspace_create.PATH,
                str(workspace_admin.populate("/workspace/admin", 0)),
            )

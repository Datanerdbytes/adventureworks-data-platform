"""Directory filters, member permissions and activity paging without live services."""

import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from flask import g
from werkzeug.exceptions import BadRequest, Forbidden

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from auth_fixtures import WORKSPACE, CONFIG, FakeGateway, csrf_headers
from governance import GovernanceError
from pages import workspace_admin, workspace_members

OTHER = {
    **WORKSPACE,
    "id": "55555555-5555-5555-5555-555555555555",
    "name": "Operations",
    "role": "admin",
}
MEMBER = {
    "workspace_id": WORKSPACE["id"],
    "workspace_name": WORKSPACE["name"],
    "user_id": "44444444-4444-4444-4444-444444444444",
    "email": "member@example.test",
    "role": "owner",
    "active": True,
    "email_confirmed": True,
    "created_at": "2026-10-12T00:00:00Z",
    "updated_at": "2026-10-13T00:00:00Z",
}


class WorkspaceMembersTests(unittest.TestCase):
    def context(self):
        request = app.server.test_request_context()
        request.push()
        self.addCleanup(request.pop)
        g.workspace = WORKSPACE
        g.workspace_context = {
            "workspaces": [WORKSPACE, OTHER],
            "platform_admin": False,
        }
        g.auth_user = {"id": "22222222-2222-2222-2222-222222222222"}
        g.governance = Mock()

    def test_layout_does_not_query_and_scope_is_server_authorized(self):
        self.context()
        workspace_members.layout()
        workspace_admin.layout()
        g.governance.rpc.assert_not_called()
        choices, selected = workspace_members.load_scopes(workspace_members.PATH, "")
        self.assertEqual(selected, WORKSPACE["id"])
        self.assertEqual(len(choices), 3)
        with self.assertRaises(Forbidden):
            workspace_members.load_scopes(workspace_members.PATH, "?workspace=foreign")
        g.workspace_context["workspaces"] = [{**WORKSPACE, "role": "viewer"}]
        with self.assertRaises(Forbidden):
            workspace_members.resolve_scope(workspace_members.ALL)

    def test_filters_apply_before_paging_and_reset_old_offsets(self):
        self.context()
        g.governance.rpc.return_value = {"members": [MEMBER], "total": 24, "offset": 0}
        with patch.object(
            workspace_members, "ctx", Mock(triggered_id="workspace-members-scope")
        ):
            result = workspace_members.load_members(
                workspace_members.PATH,
                workspace_members.ALL,
                " member@ ",
                "owner",
                "active",
                0,
                0,
                {"offset": 30},
            )
        g.governance.rpc.assert_called_once_with(
            "workspace_members_directory",
            p_workspace=None,
            p_offset=0,
            p_query="member@",
            p_role="owner",
            p_active=True,
        )
        self.assertEqual(result[0][0]["role_label"], "Owner")
        self.assertEqual(result[0][0]["status"], "Active")
        self.assertEqual(result[1], [])
        self.assertEqual(result[4:6], (True, False))
        with patch.object(
            workspace_members, "ctx", Mock(triggered_id="workspace-members-next")
        ):
            workspace_members.load_members(
                workspace_members.PATH,
                WORKSPACE["id"],
                "",
                workspace_members.ALL,
                workspace_members.ALL,
                0,
                1,
                {"offset": 10, "total": 24},
            )
        self.assertEqual(g.governance.rpc.call_args.kwargs["p_offset"], 20)
        with self.assertRaises(Forbidden):
            workspace_members.load_members(
                workspace_members.PATH, "foreign", "", "owner", "active", 0, 0, {}
            )
        with self.assertRaises(BadRequest):
            workspace_members.load_members(
                workspace_members.PATH,
                WORKSPACE["id"],
                "",
                "forged",
                "active",
                0,
                0,
                {},
            )

    def test_empty_and_failure_do_not_keep_stale_member_data(self):
        self.context()
        with patch.object(
            workspace_members, "ctx", Mock(triggered_id="workspace-members-search")
        ):
            g.governance.rpc.return_value = {"members": [], "total": 0, "offset": 0}
            empty = workspace_members.load_members(
                workspace_members.PATH,
                WORKSPACE["id"],
                "absent",
                workspace_members.ALL,
                workspace_members.ALL,
                0,
                0,
                {},
            )
            self.assertEqual(empty[0], [])
            self.assertEqual(empty[4:6], (True, True))
            g.governance.rpc.side_effect = GovernanceError(
                "private service failure", 503
            )
            failure = workspace_members.load_members(
                workspace_members.PATH,
                WORKSPACE["id"],
                "",
                workspace_members.ALL,
                workspace_members.ALL,
                0,
                0,
                {},
            )
            self.assertEqual(failure[0:2], ([], []))
            self.assertNotIn("private service failure", str(failure))

    def test_member_details_refetch_canonical_role_and_both_identifiers(self):
        self.context()
        g.governance.rpc.return_value = {"members": [MEMBER]}
        forged = {**MEMBER, "role": "viewer", "active": False}
        with patch.object(
            workspace_members, "ctx", Mock(triggered_id="workspace-members-view")
        ):
            result = workspace_members.open_member(1, 0, [forged], WORKSPACE["id"])
        self.assertTrue(result[0])
        self.assertIn("value='owner'", str(result[1]))
        g.governance.rpc.assert_called_once_with(
            "workspace_members_directory",
            p_workspace=WORKSPACE["id"],
            p_user=MEMBER["user_id"],
            p_offset=0,
        )
        with self.assertRaises(Forbidden):
            workspace_members.selected_member(
                {**MEMBER, "workspace_id": "foreign"}, workspace_members.ALL
            )
        with self.assertRaises(Forbidden):
            workspace_members.selected_member(MEMBER, OTHER["id"])

    def test_cross_workspace_admin_cannot_edit_owner_or_promote_viewer(self):
        self.context()
        target = {**MEMBER, "workspace_id": OTHER["id"]}
        g.governance.rpc.return_value = {"members": [target]}
        with self.assertRaises(Forbidden):
            workspace_members.update_member(
                1, target, "viewer", "active", workspace_members.ALL
            )
        self.assertFalse(
            any(
                c.args[0] == "change_workspace_member"
                for c in g.governance.rpc.call_args_list
            )
        )
        target = {**target, "role": "viewer"}
        g.governance.rpc.return_value = {"members": [target]}
        with self.assertRaises(Forbidden):
            workspace_members.update_member(
                1, target, "owner", "active", workspace_members.ALL
            )
        g.governance.rpc.reset_mock()
        result = workspace_members.update_member(
            1, target, "viewer", "revoked", workspace_members.ALL
        )
        g.governance.rpc.assert_any_call(
            "change_workspace_member",
            p_workspace=OTHER["id"],
            p_user=MEMBER["user_id"],
            p_role="viewer",
            p_active=False,
        )
        self.assertIn("workspace=__all__", result[1])

    def test_last_owner_error_stays_visible_without_reloading(self):
        self.context()
        g.governance.rpc.side_effect = [
            {"members": [MEMBER]},
            GovernanceError("Cannot remove the last active owner", 400),
        ]
        result = workspace_members.update_member(
            1, MEMBER, "viewer", "revoked", WORKSPACE["id"]
        )
        self.assertIn("last active owner", str(result[0]))
        self.assertIs(result[1], workspace_members.no_update)

    def test_activity_uses_its_own_bounded_history_page(self):
        self.context()
        event = dict(
            action="member_changed",
            actor_email="owner@example.test",
            created_at="2026-10-15T12:00:00+08:00",
        )
        g.governance.rpc.return_value = {"events": [event], "total": 28, "offset": 25}
        rendered = str(workspace_admin.populate_activity("/workspace/admin", 25))
        g.governance.rpc.assert_called_once_with(
            "workspace_governance_activity", p_workspace=WORKSPACE["id"], p_offset=25
        )
        self.assertIn("26–26 of 28 events", rendered)
        self.assertIn("15 Oct 2026 · 04:00 UTC", rendered)
        self.assertIn("owner@example.test", rendered)
        with patch.object(
            workspace_admin, "ctx", Mock(triggered_id="workspace-admin-activity-next")
        ):
            self.assertEqual(
                workspace_admin.page_activity(0, 1, 5, {"offset": 5, "total": 28}), 10
            )
        g.governance.rpc.return_value = {"events": [], "total": 0, "offset": 0}
        self.assertIn(
            "No governance activity yet",
            str(workspace_admin.populate_activity("/workspace/admin", 0)),
        )

    def test_overview_replaces_member_form_with_directory_link(self):
        self.context()
        g.governance.rpc.return_value = dict(
            members=[], approvals=[], events=[], member_count=3, approval_count=0
        )
        rendered = str(workspace_admin.populate("/workspace/admin", 0))
        self.assertIn(workspace_members.PATH, rendered)
        self.assertNotIn("workspace-admin-member-active", rendered)
        self.assertIn("workspace-admin-activity", rendered)

    def test_directory_direct_route_denies_viewer(self):
        with (
            patch.dict(app.server.config, CONFIG),
            patch.dict(
                app.server.extensions, {"supabase_gateway_factory": FakeGateway}
            ),
        ):
            app.server.extensions["auth_limiter"].reset()
            client = app.server.test_client()
            client.post(
                "/auth/session",
                json={"access_token": "viewer"},
                headers=csrf_headers(client),
            )
            self.assertEqual(client.get(workspace_members.PATH).status_code, 403)

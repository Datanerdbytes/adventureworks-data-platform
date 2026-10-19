"""Account management boundaries with mocked Supabase administration."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import g
from dash.exceptions import PreventUpdate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from auth_fixtures import CONFIG, FakeGateway, token, csrf_headers
import user_admin as admin
from pages import user_management as page

OWNER = {
    "id": "11111111-1111-4111-8111-111111111111",
    "email": "owner@example.test",
    "email_confirmed_at": "2026-10-19",
    "app_metadata": {"qe_role": "admin", "qe_owner": True},
}
MEMBER = {
    "id": "22222222-2222-4222-8222-222222222222",
    "email": "member@example.test",
    "email_confirmed_at": "2026-10-19",
    "app_metadata": {},
}


class UserAdminTests(unittest.TestCase):
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
        self.client.set_cookie("aw_access", token())
        blocked = patch(
            "user_admin.build_opener", side_effect=AssertionError("No live account I/O")
        )
        blocked.start()
        self.addCleanup(blocked.stop)

    def test_roles_are_only_from_confirmed_server_metadata(self):
        self.assertFalse(
            admin.is_admin(dict(MEMBER, user_metadata={"qe_role": "admin"}))
        )
        self.assertFalse(admin.is_admin(dict(OWNER, email_confirmed_at=None)))
        self.assertTrue(admin.is_admin(OWNER))
        for until in ("invalid", 42, "2999-01-01T00:00:00Z"):
            self.assertTrue(admin.account_suspended(dict(MEMBER, banned_until=until)))

    def test_directory_is_bounded_and_projects_public_fields(self):
        with app.server.test_request_context():
            g.auth_user = OWNER
            with patch.object(
                admin,
                "_service_request",
                return_value={
                    "users": [
                        dict(
                            MEMBER,
                            encrypted_password="never-return",  # pragma: allowlist secret (synthetic test data or non-secret feature flag)
                            identities=["private"],
                        )
                    ]
                },
            ) as remote:
                result = admin.list_users(2)
                self.assertEqual(
                    remote.call_args.args[:2], ("GET", "?page=2&per_page=25")
                )
                self.assertNotIn("private", str(result))
                self.assertNotIn("encrypted_password", str(result))
            for bad in (True, 0, -1, "2", 100001):
                with self.assertRaises(admin.AdminError):
                    admin.list_users(bad)

    def test_access_guards_and_current_target_rechecked_before_mutation(self):
        with app.server.test_request_context():
            g.auth_user = OWNER
            for target, action, code in (
                (OWNER, "suspend", "self_change"),
                (
                    dict(MEMBER, app_metadata={"qe_owner": True}),
                    "grant_admin",
                    "owner_protected",
                ),
                (
                    dict(MEMBER, app_metadata={"qe_role": "admin"}),
                    "suspend",
                    "protected_account",
                ),
                (
                    dict(MEMBER, email_confirmed_at=None),
                    "grant_admin",
                    "verification_required",
                ),
                (
                    dict(MEMBER, app_metadata={"qe_suspended": True}),
                    "grant_admin",
                    "verification_required",
                ),
            ):
                with patch.object(
                    admin, "_service_request", return_value=target
                ) as service:
                    with self.assertRaises(admin.AdminError) as caught:
                        admin.update_access(target["id"], action)
                    self.assertEqual(caught.exception.code, code)
                    self.assertFalse(
                        any(c.args[0] == "PUT" for c in service.call_args_list)
                    )
            with (
                patch.object(admin, "_service_request", return_value=MEMBER) as service,
                patch("password_auth._request", return_value={"ready": False}),
            ):
                with self.assertRaises(admin.AdminError):
                    admin.update_access(MEMBER["id"], "grant_admin")
                self.assertFalse(
                    any(c.args[0] == "PUT" for c in service.call_args_list)
                )
            with (
                patch.object(admin, "_service_request", return_value=MEMBER) as service,
                patch("password_auth._request", return_value={"ready": True}),
            ):
                admin.update_access(MEMBER["id"], "grant_admin")
                self.assertEqual(
                    service.call_args.args[2], {"app_metadata": {"qe_role": "admin"}}
                )

    def test_deletion_requires_owner_suspension_email_and_installed_guard(self):
        suspended = dict(MEMBER, app_metadata={"qe_suspended": True})
        with app.server.test_request_context():
            g.auth_user = dict(OWNER, app_metadata={"qe_role": "admin"})
            with self.assertRaises(admin.AdminError):
                admin.delete_account(MEMBER["id"], MEMBER["email"])
            g.auth_user = OWNER
            for target, confirmation, guard in (
                (MEMBER, MEMBER["email"], True),
                (suspended, "wrong@example.test", True),
                (suspended, MEMBER["email"], False),
                (
                    dict(
                        suspended,
                        app_metadata={"qe_role": "admin", "qe_suspended": True},
                    ),
                    MEMBER["email"],
                    True,
                ),
            ):
                with (
                    patch.object(
                        admin, "_service_request", return_value=target
                    ) as service,
                    patch("password_auth._request", return_value={"ready": guard}),
                ):
                    with self.assertRaises(admin.AdminError):
                        admin.delete_account(MEMBER["id"], confirmation)
                    self.assertFalse(
                        any(c.args[0] == "DELETE" for c in service.call_args_list)
                    )
            with (
                patch.object(
                    admin, "_service_request", return_value=suspended
                ) as service,
                patch("password_auth._request", return_value={"ready": True}),
            ):
                admin.delete_account(MEMBER["id"], MEMBER["email"])
                self.assertEqual(service.call_args.args[0], "DELETE")

    def test_api_mutation_origin_csrf_and_member_role_boundaries(self):
        url = f'/api/admin/users/{MEMBER["id"]}'
        with patch.object(admin, "_service_request") as service:
            for method, body in (
                ("PATCH", {"action": "suspend"}),
                ("DELETE", {"confirmation_email": MEMBER["email"]}),
            ):
                self.assertEqual(
                    self.client.open(
                        url,
                        method=method,
                        json=body,
                        headers={"Origin": "http://localhost"},
                    ).status_code,
                    403,
                )
                headers = csrf_headers(self.client)
                headers["Origin"] = "https://foreign.test"
                self.assertEqual(
                    self.client.open(
                        url, method=method, json=body, headers=headers
                    ).status_code,
                    403,
                )
            self.client.set_cookie("aw_access", token("viewer"))
            self.assertEqual(
                self.client.patch(
                    url, json={"action": "suspend"}, headers=csrf_headers(self.client)
                ).status_code,
                403,
            )
            service.assert_not_called()
        self.client.set_cookie("aw_access", token())
        with patch.object(
            admin, "update_access", return_value="Access restored."
        ) as update:
            result = self.client.patch(
                url, json={"action": "restore"}, headers=csrf_headers(self.client)
            )
            self.assertEqual(result.status_code, 200)
            update.assert_called_once_with(MEMBER["id"], "restore")

    def test_layout_does_not_load_directory_and_selection_explains_guards(self):
        with app.server.test_request_context():
            g.auth_user = OWNER
            with patch.object(
                admin,
                "_service_request",
                side_effect=AssertionError("No layout queries"),
            ):
                self.assertIsNotNone(page.layout())
            protected = admin._public_user(OWNER)
            self.assertEqual(
                page.selected_account([protected])[1:], (True, True, True, True)
            )
            self.assertTrue(page.deletion_available([protected]))
            self.assertTrue(page.deletion_available([admin._public_user(MEMBER)]))
            with self.assertRaises(PreventUpdate):
                page.load_directory("/dashboard", 1, 0, 0)
            with patch.object(
                page,
                "list_users",
                side_effect=admin.AdminError("admin_unavailable", 503),
            ):
                self.assertEqual(page.load_directory("/admin/users", 1, 0, 0)[0], [])

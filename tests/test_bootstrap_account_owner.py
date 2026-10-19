"""Operator bootstrap is explicit, verified and preserves a single owner."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import bootstrap_account_owner as bootstrap

USER = {
    "id": "11111111-1111-4111-8111-111111111111",
    "email": "chosen@example.test",
    "email_confirmed_at": "2026-10-19",
    "app_metadata": {},
}


class BootstrapOwnerTests(unittest.TestCase):
    def test_dry_run_never_assigns_permissions(self):
        with patch.object(
            bootstrap, "_service_request", return_value={"users": [USER]}
        ) as remote:
            self.assertIn("--apply", bootstrap.bootstrap("CHOSEN@example.test"))
            self.assertTrue(all(c.args[0] == "GET" for c in remote.call_args_list))

    def test_apply_uses_only_explicit_verified_owner(self):
        with patch.object(
            bootstrap, "_service_request", side_effect=[{"users": [USER]}, {}]
        ) as remote:
            self.assertEqual(
                bootstrap.bootstrap(USER["email"], True), "Initial owner configured."
            )
            self.assertEqual(
                remote.call_args.args,
                (
                    "PUT",
                    f'/{USER["id"]}',
                    {"app_metadata": {"qe_role": "admin", "qe_owner": True}},
                ),
            )

    def test_missing_unverified_suspended_or_different_owner_refused(self):
        for users in (
            [],
            [dict(USER, email_confirmed_at=None)],
            [dict(USER, app_metadata={"qe_suspended": True})],
            [
                USER,
                dict(
                    USER,
                    id="other",
                    email="other@example.test",
                    app_metadata={"qe_owner": True},
                ),
            ],
        ):
            with (
                self.subTest(users=users),
                patch.object(
                    bootstrap, "_service_request", return_value={"users": users}
                ) as remote,
            ):
                with self.assertRaises(ValueError):
                    bootstrap.bootstrap(USER["email"], True)
                self.assertTrue(all(c.args[0] == "GET" for c in remote.call_args_list))

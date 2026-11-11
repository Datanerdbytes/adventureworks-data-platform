"""The password operator tool is explicit, interactive and metadata preserving."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import set_account_password as tool

USER = {
    "id": "22222222-2222-4222-8222-222222222222",
    "email": "owner@example.test",
    "email_confirmed_at": "2026-10-12",
    "app_metadata": {"qe_owner": True, "qe_role": "admin", "provider": "google"},
}
SECRET = "a-long-enough-secret"  # pragma: allowlist secret (synthetic fixture)


class SetAccountPasswordTests(unittest.TestCase):
    def test_dry_run_reports_state_without_changing_anything(self):
        with patch.object(
            tool, "_service_request", return_value={"users": [USER]}
        ) as remote:
            account = tool.find_account("OWNER@example.test")
            self.assertEqual(account["id"], USER["id"])
            self.assertTrue(
                all(call.args[0] == "GET" for call in remote.call_args_list)
            )

    def test_apply_sets_only_the_password_and_keeps_governance_metadata(self):
        with patch.object(
            tool,
            "_service_request",
            side_effect=[{"users": [USER]}, {}, {"users": [USER]}],
        ) as remote:
            message = tool.set_password(USER["email"], SECRET)
        self.assertIn("Password updated", message)
        self.assertIn("qe_owner", message)
        self.assertEqual(
            remote.call_args_list[1].args,
            ("PUT", f"/{USER['id']}", {"password": SECRET, "email_confirm": True}),
        )

    def test_missing_account_is_refused_without_a_write(self):
        with patch.object(
            tool, "_service_request", return_value={"users": []}
        ) as remote:
            with self.assertRaises(ValueError):
                tool.set_password(USER["email"], SECRET)
            self.assertTrue(
                all(call.args[0] == "GET" for call in remote.call_args_list)
            )

    def test_short_password_is_refused_before_any_request(self):
        with patch.object(tool, "_service_request") as remote:
            with self.assertRaises(ValueError):
                tool.set_password(USER["email"], "short")
            remote.assert_not_called()

    def test_unconfirmed_account_is_refused(self):
        unconfirmed = dict(USER, email_confirmed_at=None)
        with patch.object(
            tool, "_service_request", return_value={"users": [unconfirmed]}
        ):
            with self.assertRaises(ValueError):
                tool.find_account(USER["email"])

    def test_prompt_requires_a_matching_long_password_without_echoing(self):
        with patch.object(tool.getpass, "getpass", side_effect=[SECRET, SECRET]):
            self.assertEqual(tool.prompt_password(), SECRET)
        with patch.object(
            tool.getpass, "getpass", side_effect=[SECRET, "other-secret"]
        ):
            with self.assertRaises(ValueError):
                tool.prompt_password()
        with patch.object(tool.getpass, "getpass", side_effect=["short", "short"]):
            with self.assertRaises(ValueError):
                tool.prompt_password()

    def test_password_is_never_taken_from_the_command_line_or_printed(self):
        source = Path(tool.__file__).read_text()
        self.assertNotIn("args.password", source)
        self.assertNotIn("--password", source)
        self.assertNotIn("print(password", source)
        self.assertNotIn("print(prompt_password()", source)


if __name__ == "__main__":
    unittest.main()

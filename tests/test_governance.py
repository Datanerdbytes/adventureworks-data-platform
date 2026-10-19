"""REST error handling and administration callbacks are tested without services."""

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from governance import SupabaseGateway, GovernanceError
from auth import auth_configuration_error, install_auth
from auth_fixtures import CONFIG
from flask import Flask


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

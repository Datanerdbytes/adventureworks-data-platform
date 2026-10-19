"""Offline boundaries for runtime-only container credentials."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "vercel_start", Path(__file__).resolve().parents[1] / "scripts/vercel_start.py"
)
assert SPEC is not None and SPEC.loader is not None
startup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(startup)


class VercelCredentialTests(unittest.TestCase):
    def test_materializes_private_runtime_file_and_removes_json_from_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            value = json.dumps({"type": "service_account", "project_id": "fixture"})
            with (
                patch.dict(os.environ, {"GOOGLE_CREDENTIALS_JSON": value}, clear=True),
                patch.object(startup.tempfile, "tempdir", directory),
            ):
                startup.configure_google_credentials()
                path = Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
                self.assertEqual(path.parent, Path(directory))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(json.loads(path.read_text()), json.loads(value))
                self.assertNotIn("GOOGLE_CREDENTIALS_JSON", os.environ)

    def test_unset_json_keeps_existing_adc_configuration(self):
        with patch.dict(
            os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/fixture/adc"}, clear=True
        ):
            startup.configure_google_credentials()
            self.assertEqual(
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"], "/fixture/adc"
            )

    def test_invalid_json_or_credential_type_fails_without_exposing_value(self):
        for value in ["sensitive-fixture", "[]", '{"type":"authorized_user"}']:
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"GOOGLE_CREDENTIALS_JSON": value}, clear=True),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    startup.configure_google_credentials()
                self.assertNotIn(value, str(caught.exception))
                self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", os.environ)

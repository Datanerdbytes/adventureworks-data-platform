"""Offline boundaries for the shipped DuckDB artifact and container startup."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vercel_start", REPO_ROOT / "scripts/vercel_start.py"
)
assert SPEC is not None and SPEC.loader is not None
startup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(startup)

sys.path.insert(0, str(REPO_ROOT / "my-dash-app"))
import warehouse_client  # noqa: E402


class ArtifactFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "analytics.duckdb"

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.temp.cleanup()

    def build(self, schema="gold_adventureworks"):
        connection = duckdb.connect(str(self.path))
        connection.execute(f"CREATE SCHEMA {schema}")
        connection.execute(f"CREATE TABLE {schema}.fct_sales (sales_key INTEGER)")
        connection.close()
        return self.path


class AnalyticsArtifactValidationTests(unittest.TestCase):
    def test_readable_artifact_with_gold_schema_passes(self):
        with ArtifactFixture() as fixture:
            path = fixture.build()
            with patch.dict(os.environ, {"GOLD_DATABASE_PATH": str(path)}, clear=False):
                self.assertEqual(startup.validate_analytics_artifact(), path)

    def test_missing_artifact_fails_with_build_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.duckdb"
            with patch.dict(os.environ, {"GOLD_DATABASE_PATH": str(path)}, clear=False):
                with self.assertRaises(RuntimeError) as caught:
                    startup.validate_analytics_artifact()
        message = str(caught.exception)
        self.assertIn(str(path), message)
        self.assertIn("export_gold_duckdb.py", message)

    def test_empty_artifact_fails_instead_of_serving_broken_reports(self):
        with ArtifactFixture() as fixture:
            path = fixture.build(schema="public")
            with patch.dict(os.environ, {"GOLD_DATABASE_PATH": str(path)}, clear=False):
                with self.assertRaises(RuntimeError) as caught:
                    startup.validate_analytics_artifact()
        self.assertIn("no gold_adventureworks tables", str(caught.exception))

    def test_unreadable_file_is_reported_without_leaking_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analytics.duckdb"
            path.write_text("sensitive-fixture")
            with patch.dict(os.environ, {"GOLD_DATABASE_PATH": str(path)}, clear=False):
                with self.assertRaises(RuntimeError) as caught:
                    startup.validate_analytics_artifact()
        self.assertIn("not a readable DuckDB database", str(caught.exception))
        self.assertNotIn("sensitive-fixture", str(caught.exception))

    def test_repository_ships_a_valid_artifact(self):
        environment = dict(os.environ)
        environment.pop("GOLD_DATABASE_PATH", None)
        with patch.dict(os.environ, environment, clear=True):
            path = startup.validate_analytics_artifact()
        self.assertEqual(path, warehouse_client.DEFAULT_ARTIFACT_PATH)
        self.assertTrue(path.is_file())


class ServerCommandTests(unittest.TestCase):
    def test_default_port_and_app_directory(self):
        environment = dict(os.environ)
        environment.pop("PORT", None)
        with patch.dict(os.environ, environment, clear=True):
            command = startup.server_command()
        self.assertEqual(command[0], "gunicorn")
        self.assertEqual(command[command.index("--bind") + 1], "0.0.0.0:8050")
        self.assertEqual(
            command[command.index("--chdir") + 1], str(startup.APP_DIRECTORY)
        )
        self.assertEqual(command[-1], "app:server")

    def test_configured_port_is_used(self):
        with patch.dict(os.environ, {"PORT": "9000"}, clear=False):
            command = startup.server_command()
        self.assertEqual(command[command.index("--bind") + 1], "0.0.0.0:9000")

    def test_invalid_port_fails_closed(self):
        for value in ["", "http", "0", "65536", "-1"]:
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"PORT": value}, clear=False),
            ):
                with self.assertRaises(RuntimeError):
                    startup.server_command()

    def test_main_validates_before_replacing_the_process(self):
        with (
            patch.object(startup, "validate_analytics_artifact") as validate,
            patch.object(startup.os, "execvp") as execvp,
            patch.dict(os.environ, {"PORT": "8050"}, clear=False),
        ):
            startup.main()
        validate.assert_called_once_with()
        self.assertEqual(execvp.call_args.args[0], "gunicorn")


if __name__ == "__main__":
    unittest.main()

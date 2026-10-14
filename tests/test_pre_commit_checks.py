"""Hook safety: isolate Redis configuration and fail closed on failed checks."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import pre_commit_checks


class PreCommitChecksTests(unittest.TestCase):
    def test_python_tests_override_storage_without_mutating_parent_environment(self):
        with (
            patch.dict(
                os.environ,
                RATE_LIMIT_ENVIRONMENT="production",
                RATE_LIMIT_REDIS_URL="redis://fixture-only",
                RATE_LIMIT_TRUST_PROXY="1",
            ),
            patch.object(sys, "argv", ["pre_commit_checks.py", "python-tests"]),
            patch.object(pre_commit_checks, "run", return_value=0) as run,
        ):
            self.assertEqual(pre_commit_checks.main(), 0)
            command, environment = run.call_args.args
            self.assertEqual(command[-4:], ["discover", "-s", "tests", "-v"])
            self.assertEqual(environment["RATE_LIMIT_ENVIRONMENT"], "testing")
            self.assertEqual(environment["RATE_LIMIT_REDIS_URL"], "")
            self.assertEqual(environment["RATE_LIMIT_TRUST_PROXY"], "")
            self.assertEqual(environment["RATE_LIMIT_TRUSTED_PROXY_CIDRS"], "")
            self.assertEqual(os.environ["RATE_LIMIT_ENVIRONMENT"], "production")
            self.assertEqual(os.environ["RATE_LIMIT_REDIS_URL"], "redis://fixture-only")

    def test_audit_stops_if_locked_export_fails(self):
        with (
            patch.object(sys, "argv", ["pre_commit_checks.py", "dependency-audit"]),
            patch.object(pre_commit_checks.shutil, "which", return_value="uv"),
            patch.object(pre_commit_checks, "run", return_value=1) as run,
        ):
            self.assertEqual(pre_commit_checks.main(), 1)
            run.assert_called_once()
            self.assertIn("--locked", run.call_args.args[0])

    def test_audit_propagates_advisory_failure(self):
        with (
            patch.object(sys, "argv", ["pre_commit_checks.py", "dependency-audit"]),
            patch.object(pre_commit_checks.shutil, "which", return_value="uv"),
            patch.object(pre_commit_checks, "run", side_effect=[0, 1]) as run,
        ):
            self.assertEqual(pre_commit_checks.main(), 1)
            self.assertIn("--locked", run.call_args_list[0].args[0])
            self.assertIn("--strict", run.call_args_list[1].args[0])
            self.assertNotIn("quiet", run.call_args_list[1].kwargs)

    def test_javascript_syntax_failure_stops_without_running_code(self):
        with (
            patch.object(
                sys,
                "argv",
                ["pre_commit_checks.py", "javascript-syntax", "first.js", "second.js"],
            ),
            patch.object(pre_commit_checks, "run", return_value=1) as run,
        ):
            self.assertEqual(pre_commit_checks.main(), 1)
            run.assert_called_once_with(["node", "--check", "--", "first.js"])

"""Hook safety: fail closed on failed checks and never touch external services."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import pre_commit_checks


class PreCommitChecksTests(unittest.TestCase):
    def test_python_tests_run_offline_unittest_suite(self):
        with (
            patch.object(sys, "argv", ["pre_commit_checks.py", "python-tests"]),
            patch.object(pre_commit_checks, "run", return_value=0) as run,
        ):
            self.assertEqual(pre_commit_checks.main(), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[-4:], ["discover", "-s", "tests", "-v"])

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

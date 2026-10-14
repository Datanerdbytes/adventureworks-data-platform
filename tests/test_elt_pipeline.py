import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import elt_pipeline
from elt_pipeline import (
    resolve_destination_config,
    is_production_destination,
    validate_confirmation,
    run_elt_migration,
    PRODUCTION_PROJECT_ID,
    TABLES_TO_MIGRATE,
    PipelineConfigurationError,
    PipelineConfirmationError,
)


class ResolveDestinationConfigTests(unittest.TestCase):
    def test_missing_project_id(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PipelineConfigurationError):
                resolve_destination_config()

    def test_missing_dataset_id(self):
        with patch.dict(os.environ, {"GBQ_PROJECT_ID": "test-project"}, clear=True):
            with self.assertRaises(PipelineConfigurationError):
                resolve_destination_config()

    def test_unqualified_dataset(self):
        with patch.dict(
            os.environ,
            {"GBQ_PROJECT_ID": "test-project", "GBQ_DATASET_ID": "test_dataset"},
            clear=True,
        ):
            project, dataset, dest = resolve_destination_config()
            self.assertEqual(project, "test-project")
            self.assertEqual(dataset, "test_dataset")
            self.assertEqual(dest, "test-project.test_dataset")

    def test_qualified_dataset_matching(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": "test-project",
                "GBQ_DATASET_ID": "test-project.test_dataset",
            },
            clear=True,
        ):
            project, dataset, dest = resolve_destination_config()
            self.assertEqual(project, "test-project")
            self.assertEqual(dataset, "test_dataset")
            self.assertEqual(dest, "test-project.test_dataset")

    def test_qualified_dataset_conflict(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": "test-project",
                "GBQ_DATASET_ID": "other-project.test_dataset",
            },
            clear=True,
        ):
            with self.assertRaises(PipelineConfigurationError) as cm:
                resolve_destination_config()
            self.assertIn("conflicts with", str(cm.exception))
            self.assertIn("other-project", str(cm.exception))
            self.assertIn("test-project", str(cm.exception))


class IsProductionDestinationTests(unittest.TestCase):
    def test_production_project(self):
        self.assertTrue(is_production_destination(PRODUCTION_PROJECT_ID))

    def test_non_production_project(self):
        self.assertFalse(is_production_destination("some-other-project"))


class ValidateConfirmationTests(unittest.TestCase):
    def test_non_production_no_confirmation_needed(self):
        validate_confirmation(
            "test-project",
            "test_dataset",
            "test-project.test_dataset",
            False,
            None,
            True,
        )

    def test_production_missing_confirm_production(self):
        with self.assertRaises(PipelineConfirmationError) as cm:
            validate_confirmation(
                PRODUCTION_PROJECT_ID,
                "raw_adventureworks",
                f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
                False,
                None,
                True,
            )
        self.assertIn("--confirm-production", str(cm.exception))

    def test_production_missing_destination(self):
        with self.assertRaises(PipelineConfirmationError) as cm:
            validate_confirmation(
                PRODUCTION_PROJECT_ID,
                "raw_adventureworks",
                f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
                True,
                None,
                True,
            )
        self.assertIn("--destination", str(cm.exception))

    def test_production_wrong_destination(self):
        with self.assertRaises(PipelineConfirmationError) as cm:
            validate_confirmation(
                PRODUCTION_PROJECT_ID,
                "raw_adventureworks",
                f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
                True,
                "wrong-destination",
                True,
            )
        self.assertIn("mismatch", str(cm.exception))
        self.assertIn("wrong-destination", str(cm.exception))

    def test_production_correct_confirmation(self):
        validate_confirmation(
            PRODUCTION_PROJECT_ID,
            "raw_adventureworks",
            f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
            True,
            f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
            True,
        )


class DryRunTests(unittest.TestCase):
    def test_dry_run_no_external_calls(self):
        with patch.dict(
            os.environ,
            {"GBQ_PROJECT_ID": "test-project", "GBQ_DATASET_ID": "test_dataset"},
            clear=True,
        ):
            with patch("elt_pipeline.get_postgres_engine") as mock_pg:
                with patch("elt_pipeline.bigquery.Client") as mock_bq:
                    with patch("elt_pipeline._load_env"):
                        run_elt_migration(dry_run=True)
                        mock_pg.assert_not_called()
                        mock_bq.assert_not_called()

    def test_dry_run_production_missing_confirmations(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
            },
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                run_elt_migration(
                    dry_run=True, confirm_production=False, destination=None
                )


class CallableApiTests(unittest.TestCase):
    def test_direct_call_without_confirmation_fails_for_production(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
            },
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                with patch("elt_pipeline.get_postgres_engine") as mock_pg:
                    with patch("elt_pipeline.bigquery.Client") as mock_bq:
                        with self.assertRaises(PipelineConfirmationError):
                            run_elt_migration()
                        mock_pg.assert_not_called()
                        mock_bq.assert_not_called()

    def test_authorized_execution_submits_jobs(self):
        mock_records = [
            MagicMock(_mapping={"id": 1, "name": "test"}),
        ]
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_records
        mock_conn.execute.return_value = mock_result

        mock_bq_client = MagicMock()
        mock_job = MagicMock()
        mock_bq_client.load_table_from_dataframe.return_value = mock_job

        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
            },
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                with patch(
                    "elt_pipeline.get_postgres_engine", return_value=mock_engine
                ):
                    with patch(
                        "elt_pipeline.bigquery.Client", return_value=mock_bq_client
                    ) as mock_client_cls:
                        with patch("elt_pipeline._is_interactive", return_value=True):
                            run_elt_migration(
                                confirm_production=True,
                                destination=f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
                                interactive=True,
                            )

                            mock_client_cls.assert_called_once_with(
                                project=PRODUCTION_PROJECT_ID
                            )
                            self.assertEqual(
                                mock_bq_client.load_table_from_dataframe.call_count,
                                len(TABLES_TO_MIGRATE),
                            )

    def test_authorized_execution_handles_empty_tables(self):
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        mock_bq_client = MagicMock()

        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
            },
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                with patch(
                    "elt_pipeline.get_postgres_engine", return_value=mock_engine
                ):
                    with patch(
                        "elt_pipeline.bigquery.Client", return_value=mock_bq_client
                    ):
                        with patch("elt_pipeline._is_interactive", return_value=True):
                            run_elt_migration(
                                confirm_production=True,
                                destination=f"{PRODUCTION_PROJECT_ID}.raw_adventureworks",
                                interactive=True,
                            )

                            mock_bq_client.load_table_from_dataframe.assert_not_called()


class NoninteractiveTests(unittest.TestCase):
    def test_noninteractive_requires_explicit_inputs(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
            },
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                with patch("elt_pipeline._is_interactive", return_value=False):
                    with self.assertRaises(PipelineConfirmationError):
                        run_elt_migration()


class ExecutionTests(unittest.TestCase):
    def test_cli_exits_nonzero_on_config_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("elt_pipeline._load_env"):
                with patch.object(sys, "argv", ["elt_pipeline.py"]):
                    with self.assertRaises(SystemExit) as cm:
                        elt_pipeline.main()
                    self.assertNotEqual(cm.exception.code, 0)

    def test_cli_exits_nonzero_on_confirmation_error(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
            },
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                with patch.object(sys, "argv", ["elt_pipeline.py"]):
                    with self.assertRaises(SystemExit) as cm:
                        elt_pipeline.main()
                    self.assertEqual(cm.exception.code, 2)

    def test_cli_exits_nonzero_on_general_error(self):
        with patch.dict(
            os.environ,
            {"GBQ_PROJECT_ID": "test-project", "GBQ_DATASET_ID": "test_dataset"},
            clear=True,
        ):
            with patch("elt_pipeline._load_env"):
                with patch(
                    "elt_pipeline.get_postgres_engine",
                    side_effect=Exception("Connection failed"),
                ):
                    with patch.object(sys, "argv", ["elt_pipeline.py"]):
                        with self.assertRaises(SystemExit) as cm:
                            elt_pipeline.main()
                        self.assertEqual(cm.exception.code, 1)


class ConfigurationValidationTests(unittest.TestCase):
    def test_empty_env_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PipelineConfigurationError):
                resolve_destination_config()

    def test_partial_env_fails_closed(self):
        with patch.dict(os.environ, {"GBQ_PROJECT_ID": "test-project"}, clear=True):
            with self.assertRaises(PipelineConfigurationError):
                resolve_destination_config()

    def test_production_recognized_regardless_of_environment_label(self):
        with patch.dict(
            os.environ,
            {
                "GBQ_PROJECT_ID": PRODUCTION_PROJECT_ID,
                "GBQ_DATASET_ID": "raw_adventureworks",
                "ENVIRONMENT": "development",
            },
            clear=True,
        ):
            project_id, dataset_id, dest = resolve_destination_config()
            self.assertTrue(is_production_destination(project_id))


if __name__ == "__main__":
    unittest.main()

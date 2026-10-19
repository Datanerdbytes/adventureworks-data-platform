"""Offline preview safety, cache isolation and table callback boundaries."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from flask import Flask
from dash.exceptions import PreventUpdate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
import warehouse_tables as warehouse
from app import app
from pages import tables


def fixture(name="Products"):
    return {
        field: 2 if kind == "number" else "fixture"
        for field, _, kind in warehouse.TABLES[name]["columns"]
    }


class WarehouseTableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = Flask(__name__)
        self.server.extensions["executive_query_lock_dir"] = Path(self.temp.name)
        warehouse.cache.init_app(
            self.server,
            config={
                "CACHE_TYPE": "FileSystemCache",
                "CACHE_DIR": self.temp.name + "/cache",
                "CACHE_THRESHOLD": 500,
            },
        )
        context = self.server.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(warehouse.cache.clear)
        item = patch("warehouse_tables.bigquery.Client")
        self.factory = item.start()
        self.addCleanup(item.stop)
        self.client = self.factory.return_value.__enter__.return_value
        self.job = self.client.query.return_value
        self.job.result.return_value = [fixture()]

    def test_explicit_read_only_query_bounded_results_billing_and_stable_order(self):
        result = warehouse.load_table_preview("test-project", "gold", "Products")
        sql = self.client.query.call_args.args[0]
        config = self.client.query.call_args.kwargs["job_config"]
        self.assertIn("SELECT `product_key`,", sql)
        self.assertNotIn("SELECT *", sql)
        self.assertIn("ORDER BY `product_key` LIMIT @preview_limit", sql)
        self.assertEqual(config.maximum_bytes_billed, 100 * 1024 * 1024)
        self.assertEqual(config.query_parameters[0].value, 501)
        self.job.result.assert_called_once_with(timeout=20, max_results=501)
        self.assertFalse(result["capped"])

    def test_cache_reuses_selection_and_separates_project_dataset_and_table(self):
        def query(sql, **kwargs):
            job = Mock()
            name = (
                "Sales"
                if "fct_sales" in sql
                else "Customers" if "dim_customer" in sql else "Products"
            )
            job.result.return_value = [fixture(name)]
            return job

        self.client.query.side_effect = query
        args = ("test-project", "gold", "Products")
        baseline = warehouse.load_table_preview(*args)
        self.assertEqual(warehouse.load_table_preview(*args), baseline)
        self.assertEqual(self.client.query.call_count, 1)
        for args in [
            ("other-project", "gold", "Products"),
            ("test-project", "other_dataset", "Products"),
            ("test-project", "gold", "Customers"),
            ("test-project", "gold", "Sales"),
        ]:
            warehouse.load_table_preview(*args)
        self.assertEqual(self.client.query.call_count, 5)

    def test_cap_nulls_dates_and_numbers_remain_truthful(self):
        row = fixture()
        row.update(
            list_price=Decimal("123.45"),
            standard_cost=None,
            valid_from_date=date(2013, 1, 1),
            valid_to_date=None,
        )
        self.job.result.return_value = [row] * 501
        result = warehouse.load_table_preview("test-project", "gold", "Products")
        self.assertEqual(len(result["rows"]), 500)
        self.assertTrue(result["capped"])
        self.assertEqual(result["rows"][0]["list_price"], 123.45)
        self.assertIsNone(result["rows"][0]["standard_cost"])
        self.assertEqual(result["rows"][0]["valid_from_date"], "2013-01-01")
        identifier = next(
            c
            for c in warehouse.preview_columns("Products")
            if c["field"] == "product_id"
        )
        self.assertEqual(identifier["cellDataType"], "text")
        self.assertEqual(warehouse.preview_value("FR-R92B-58"), "FR-R92B-58")
        numeric = next(
            c
            for c in warehouse.preview_columns("Products")
            if c["field"] == "list_price"
        )
        self.assertEqual(numeric["cellDataType"], "number")
        self.assertEqual(numeric["filter"], "agNumberColumnFilter")

    def test_identifiers_and_unknown_table_rejected_before_query(self):
        for args in [
            ("bad`;DROP", "gold", "Products"),
            ("test-project", "gold.bad", "Products"),
            ("test-project", "gold", "dim_product;DROP"),
            ("test-project", "gold", None),
        ]:
            with self.assertRaises(ValueError):
                warehouse.load_table_preview(*args)
        self.factory.assert_not_called()

    def test_timeout_cancels_job_and_errors_are_not_cached_as_empty_success(self):
        self.job.result.side_effect = TimeoutError("fixture")
        with self.assertRaises(TimeoutError):
            warehouse.load_table_preview("test-project", "gold", "Products")
        self.job.cancel.assert_called_once()
        self.job.result.side_effect = None
        self.job.result.return_value = []
        self.assertEqual(
            warehouse.load_table_preview("test-project", "gold", "Products"),
            {"rows": [], "capped": False},
        )
        self.assertEqual(self.client.query.call_count, 2)

    def test_layout_and_inactive_page_do_not_load_data(self):
        with patch.object(tables, "load_table_preview") as load:
            self.assertIsNotNone(tables.layout())
            self.assertEqual(
                app.server.test_client()
                .post("/_dash-update-component", json={})
                .status_code,
                401,
            )
            with self.assertRaises(PreventUpdate):
                tables.populate("Products", None, None, "/dashboard")
            self.assertEqual(tables.populate("untrusted", None, None)[0], [])
            load.assert_not_called()

    def test_callback_distinguishes_empty_failure_and_capped_preview(self):
        with (
            patch.object(
                tables, "warehouse_location", return_value=("test-project", "gold")
            ),
            patch.object(
                tables,
                "load_table_preview",
                return_value={"rows": [fixture()], "capped": True},
            ),
        ):
            rows, _, options, message = tables.populate(
                "Products", "bike", {"pageSize": 20}
            )
            self.assertIn("First 500 rows; more rows exist", message)
            self.assertIn("test-project.gold.dim_product", message)
            self.assertEqual(options["paginationPageSize"], 20)
            self.assertEqual(options["quickFilterText"], "bike")
        with patch.object(
            tables, "load_table_preview", return_value={"rows": [], "capped": False}
        ):
            self.assertIn("No rows available", tables.populate("Products", None, {})[3])
        with patch.object(
            tables,
            "load_table_preview",
            side_effect=RuntimeError("credential must not appear"),
        ):
            result = tables.populate("Products", None, [])
            self.assertEqual(result[0], [])
            self.assertIn("unavailable", result[3])
            self.assertNotIn("credential", result[3])

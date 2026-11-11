"""Offline routing and fixture/callback regression checks."""

import sys
from unittest.mock import patch
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from data import grid_options, runs, table_rows
from pages import dashboard, monitoring, tables


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = app.server.test_client()
        preview = patch(
            "pages.tables.load_table_preview",
            return_value={
                "rows": [
                    {
                        "product_key": 100,
                        "product_name": "Warehouse fixture",
                        "list_price": 49.5,
                    }
                ],
                "capped": False,
            },
        )
        preview.start()
        self.addCleanup(preview.stop)

    def test_routes_and_shell(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        for route in (
            "/dashboard",
            "/workspace",
            "/monitoring",
            "/tables",
            "/settings",
            "/missing",
            "/_dash-layout",
            "/_dash-dependencies",
        ):
            self.assertEqual(self.client.get(route).status_code, 200)

    def test_callback_updates_tables_grid(self):
        self.client.get("/_dash-layout")
        output = next(key for key in app.callback_map if "tables-grid.rowData" in key)
        outputs = [
            {"id": "tables-grid", "property": prop}
            for prop in ("rowData", "columnDefs", "dashGridOptions")
        ] + [{"id": "tables-status", "property": "children"}]
        body = {
            "output": output,
            "outputs": outputs,
            "inputs": [
                {"id": "tables-selector", "property": "value", "value": "Products"},
                {"id": "tables-search", "property": "value", "value": ""},
                {
                    "id": "display-preferences",
                    "property": "data",
                    "value": {"pageSize": 10},
                },
                {"id": "app-location", "property": "pathname", "value": "/tables"},
            ],
            "state": [],
            "changedPropIds": ["tables-selector.value"],
        }
        response = self.client.post("/_dash-update-component", json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["response"]["tables-grid"]["rowData"]), 1)

    def test_monitoring_filters_and_preferences(self):
        figure, rows, columns, metrics, status, options = monitoring.populate(
            "Quality checks", 7, 0, {"pageSize": 20}
        )
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row["Pipeline"] == "Quality checks" for row in rows))
        self.assertEqual(options["paginationPageSize"], 20)
        self.assertIn("Synthetic demo runs", status)
        self.assertEqual(len(monitoring.populate("missing", 7, 0, {})[1]), 0)

    def test_tables_and_empty_state(self):
        rows, columns, options, message = tables.populate(
            "Products", "Bike", {"pageSize": 50}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(options["quickFilterText"], "Bike")
        self.assertEqual(options["paginationPageSize"], 50)
        self.assertEqual(tables.populate("missing", None, None)[0], [])
        self.assertEqual(grid_options(999)["paginationPageSize"], 10)

    def test_determinism_and_dashboard(self):
        self.assertEqual(runs(), runs())
        self.assertEqual(table_rows("Sales"), table_rows("Sales"))
        figure, metrics, recent, status = dashboard.populate("/dashboard")
        self.assertEqual(len(figure.data), 2)
        self.assertEqual(len(metrics), 4)
        self.assertEqual(len(recent), 3)
        self.assertIn("synthetic", status)


if __name__ == "__main__":
    unittest.main()

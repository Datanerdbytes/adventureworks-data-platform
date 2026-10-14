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
        from auth_fixtures import CONFIG, FakeGateway

        self.client = app.server.test_client()
        self.client.set_cookie("aw_access", "approved")
        self.config_patch = patch.dict(app.server.config, CONFIG)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        gateway_patch = patch.dict(
            app.server.extensions, supabase_gateway_factory=FakeGateway
        )
        gateway_patch.start()
        self.addCleanup(gateway_patch.stop)
        self.auth = {}

    def test_routes_and_shell(self):
        anonymous = app.server.test_client()
        self.assertEqual(anonymous.get("/").status_code, 200)
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
            self.assertEqual(anonymous.get(route).status_code, 401)

    def test_auth_rejects_invalid_headers(self):
        anonymous = app.server.test_client()
        for header in ("Bearer abc", "Basic !!!", "Basic YQ=="):
            self.assertEqual(
                anonymous.get(
                    "/_dash-layout", headers={"Authorization": header}
                ).status_code,
                401,
            )

    def test_auth_fails_closed_without_config(self):
        with patch.dict(app.server.config, SUPABASE_PUBLIC_KEY=""):
            self.assertEqual(self.client.get("/dashboard").status_code, 503)
            self.assertEqual(app.server.test_client().get("/").status_code, 200)

    def test_callback_cannot_spoof_public_path(self):
        body = {
            "output": "dashboard-metrics.children",
            "inputs": [{"id": "app-location", "property": "pathname", "value": "/"}],
        }
        self.assertEqual(
            app.server.test_client()
            .post("/_dash-update-component", json=body)
            .status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/_dash-update-component",
                json=body,
                headers={"Origin": "https://untrusted.example"},
            ).status_code,
            403,
        )

    def test_authenticated_callback_and_identity(self):
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
            ],
            "state": [],
            "changedPropIds": ["tables-selector.value"],
        }
        response = self.client.post(
            "/_dash-update-component", json=body, headers={"Origin": "http://localhost"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["response"]["tables-grid"]["rowData"]), 48)
        layout = self.client.get("/_dash-layout")
        self.assertIn(b"Account for owner@example.test", layout.data)
        self.assertNotIn(b"test-public-key", layout.data)
        self.assertEqual(layout.headers["Cache-Control"], "private, no-store")

    def test_public_assets_do_not_expose_dashboard(self):
        anonymous = app.server.test_client()
        with anonymous.get("/assets/landing.css") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(anonymous.get("/assets/sidebar.js").status_code, 401)
        self.assertEqual(anonymous.get("/_dash-layout?pathname=/").status_code, 401)

    def test_monitoring_filters_and_preferences(self):
        figure, rows, columns, metrics, status, options = monitoring.populate(
            "Quality checks", 7, 0, {"pageSize": 20}
        )
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row["Pipeline"] == "Quality checks" for row in rows))
        self.assertEqual(options["paginationPageSize"], 20)
        self.assertIn("Refreshed", status)
        self.assertEqual(len(monitoring.populate("missing", 7, 0, {})[1]), 0)

    def test_tables_and_empty_state(self):
        rows, columns, options, message = tables.populate(
            "Products", "Bike", {"pageSize": 50}
        )
        self.assertEqual(len(rows), 48)
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

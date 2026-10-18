"""Offline integration coverage for chart loading, feedback, and card ownership."""

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from chart_feedback import feedback
from pages import customers, dashboard, executive, growth, monitoring, wholesale
from test_growth_filters import CATALOG
from sales_filters import ALL
import plotly.graph_objects as go


def walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from walk(child)
    elif hasattr(component, "to_plotly_json"):
        yield component
        yield from walk(getattr(component, "children", []))


class ChartFeedbackTests(unittest.TestCase):
    def test_each_chart_owns_accessible_feedback_and_loading(self):
        expected = {
            dashboard: {"dashboard-activity": "dashboard-status"},
            monitoring: {"monitoring-chart": "monitoring-status"},
            executive: {
                "executive-primary": "executive-primary-status",
                "executive-secondary": "executive-secondary-status",
            },
            wholesale: {
                "wholesale-primary": "wholesale-leaderboard-status",
                "wholesale-secondary": "wholesale-secondary-status",
            },
            growth: {
                "growth-primary": "growth-primary-status",
                "growth-secondary": "growth-secondary-status",
            },
            customers: {
                "customers-primary": "customers-map-status",
                "customers-secondary": "customers-chart-status",
            },
        }
        for page, charts in expected.items():
            layout = page.layout()
            all_nodes = list(walk(layout))
            identifiers = [getattr(node, "id", None) for node in all_nodes]
            for graph_id, status_id in charts.items():
                with self.subTest(chart=graph_id):
                    self.assertEqual(identifiers.count(status_id), 1)
                    card = next(
                        node
                        for node in all_nodes
                        if getattr(node, "className", None) == "card"
                        and any(
                            getattr(child, "id", None) == graph_id
                            for child in walk(node)
                        )
                    )
                    nodes = list(walk(card))
                    status = next(
                        node for node in nodes if getattr(node, "id", None) == status_id
                    )
                    self.assertEqual(status.role, "status")
                    self.assertEqual(getattr(status, "aria-live"), "polite")
                    self.assertIn("chart-status", status.className)
                    self.assertTrue(
                        any(
                            node.__class__.__name__ == "Loading"
                            and any(
                                getattr(child, "id", None) == graph_id
                                for child in walk(node)
                            )
                            for node in nodes
                        )
                    )

    def test_empty_state_overrides_success_note_and_preserves_zero_data(self):
        empty = go.Figure()
        empty.add_annotation(text="No sales match these filters.")
        figure, message = feedback(
            empty, "Sales totals · Not normalized by number of days"
        )
        self.assertIn("No sales", message)
        self.assertFalse(figure.layout.annotations)
        self.assertFalse(figure.layout.xaxis.visible)
        self.assertTrue(empty.layout.annotations)  # Do not mutate the source figure.
        zero = go.Figure(go.Bar(x=["Measured zero"], y=[0]))
        self.assertEqual(feedback(zero)[1], "")
        self.assertIs(feedback(zero)[0], zero)
        self.assertEqual(
            feedback(zero, "A useful definition")[1], "A useful definition"
        )

    def test_executive_empty_failure_and_success_outputs(self):
        self.assertIn(
            "Waiting", executive.update_monthly_chart(None, *([ALL] * 5), "line")[1]
        )
        with (
            patch("pages.executive.normalize_filters", return_value=[None] * 5),
            patch(
                "pages.executive.load_executive_report",
                side_effect=RuntimeError("private detail"),
            ),
        ):
            figure, message = executive.update_breakdown_chart(
                CATALOG, *([ALL] * 5), "bar"
            )
            self.assertIn("reload", message)
            self.assertNotIn("private detail", message)
            self.assertFalse(figure.data)
        values = {"monthly": [], "detail": []}
        with (
            patch("pages.executive.normalize_filters", return_value=[None] * 5),
            patch("pages.executive.load_executive_report", return_value=values),
        ):
            for index in (1, 2):
                self.assertIn(
                    "No data",
                    executive.populate_chart(CATALOG, [ALL] * 5, "line", index)[1],
                )

    def test_empty_warehouse_views_have_messages_and_preserve_important_notes(self):
        cases = [
            (
                wholesale,
                "load_top_resellers",
                lambda: wholesale.populate_leaderboard(CATALOG, *([ALL] * 5)),
                1,
            ),
            (
                wholesale,
                "load_wholesale_product_mix",
                lambda: wholesale.populate_secondary("bar", CATALOG, *([ALL] * 5)),
                2,
            ),
            (
                growth,
                "load_day_type_sales",
                lambda: growth.populate_primary("day-type", CATALOG, *([ALL] * 5)),
                2,
            ),
            (
                growth,
                "load_seasonality_matrix",
                lambda: growth.populate_secondary("matrix", CATALOG, *([ALL] * 5)),
                2,
            ),
            (
                customers,
                "load_customer_demographics",
                lambda: customers.populate_region(
                    "bar", "__overview__", CATALOG, *([ALL] * 5)
                ),
                4,
            ),
            (
                customers,
                "load_customer_lifecycle",
                lambda: customers.populate_customer_chart(
                    "funnel", CATALOG, *([ALL] * 5)
                ),
                1,
            ),
            (
                customers,
                "load_customer_segment_revenue",
                lambda: customers.populate_customer_chart(
                    "income", CATALOG, *([ALL] * 5)
                ),
                1,
            ),
        ]
        for page, loader, call, status_index in cases:
            with (
                self.subTest(loader=loader),
                patch.object(page, "load_filter_catalog", return_value=CATALOG),
                patch.object(page, loader, return_value=[]),
            ):
                result = call()
                self.assertIn("No ", result[status_index])
                self.assertFalse(result[0].layout.annotations)
        self.assertIn("synthetic", dashboard.populate("/dashboard")[3].lower())

    def test_new_status_outputs_are_registered(self):
        app._setup_server()
        # Global callbacks transfer when Dash initializes the request handlers.
        for chart in ("primary", "secondary"):
            self.assertTrue(
                any(
                    f"executive-{chart}-status.children" in key
                    for key in app.callback_map
                )
            )

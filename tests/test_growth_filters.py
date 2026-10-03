import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from dash.exceptions import PreventUpdate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.growth import populate_growth, render_growth
from test_wholesale_kpis import CATALOG, ALL


def report(months):
    return dict(
        monthly=[dict(calendar_year=y, month_name=m, revenue=r) for y, m, r in months],
        gross_revenue_amount=150,
        total_orders_count=3,
        detail=[dict(units=12)],
    )


class GrowthTests(unittest.TestCase):
    def test_prior_calendar_month_and_missing_baselines(self):
        values = report([(2026, "January", 150), (2026, "March", 300)])
        history = report(
            [(2025, "December", 100), (2026, "January", 150), (2026, "March", 300)]
        )
        _, _, rows, _ = render_growth(values, history)
        self.assertEqual(rows[0]["Monthly growth (%)"], 50)
        self.assertIsNone(rows[1]["Monthly growth (%)"])
        history = report([(2025, "December", 0)])
        self.assertIsNone(render_growth(values, history)[2][0]["Monthly growth (%)"])

    def test_all_filters_and_baseline_scope(self):
        values = report([(2026, "January", 150)])
        with (
            patch("pages.growth.load_filter_catalog", return_value=CATALOG),
            patch("pages.growth.load_growth_ledger", return_value=[]) as loader,
        ):
            for selections in (
                [ALL] * 5,
                [2026, ALL, ALL, ALL, ALL],
                [ALL, "Q1", ALL, ALL, ALL],
                [ALL, ALL, "Reseller", ALL, ALL],
                [ALL, ALL, ALL, "Bikes", ALL],
                [2026, "Q1", "Reseller", "Bikes", "Road Bikes"],
            ):
                loader.reset_mock()
                result = populate_growth(CATALOG, *selections, {})
                self.assertEqual(len(result), 4)
                normalized = [None if x == ALL else x for x in selections]
                self.assertEqual(loader.call_args_list[0].args[2:], tuple(normalized))
            with self.assertRaises(PreventUpdate):
                populate_growth(CATALOG, ALL, ALL, ALL, "Clothing", "Road Bikes", {})
            loader.return_value = []
            self.assertIn(
                "No warehouse sales", populate_growth(CATALOG, *([ALL] * 5), {})[-1]
            )
            loader.side_effect = RuntimeError("private")
            self.assertIn(
                "Unable to load", populate_growth(CATALOG, *([ALL] * 5), {})[-1]
            )
            self.assertIn("Waiting", populate_growth(None, *([ALL] * 5), {})[-1])

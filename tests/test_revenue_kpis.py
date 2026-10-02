import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.executive import layout, populate_report, normalize_filters, render_report
from revenue_kpis import kpi_cards, kpi_sql


class RevenueKpiTests(unittest.TestCase):
    def test_five_cards_and_percentage_units(self):
        cards = kpi_cards(
            {
                "gross_revenue_amount": Decimal("1234567.89"),
                "gross_profit_amount": Decimal("250000.00"),
                "gross_profit_margin_percentage": Decimal("20.25"),
                "total_orders_count": 12000,
                "average_order_value_aov": Decimal("102.88"),
            }
        )
        self.assertEqual(len(cards), 5)
        self.assertEqual(
            [c.children[1].children for c in cards],
            ["$1.23M", "$250K", "20.25%", "12K", "$102.88"],
        )
        self.assertEqual(len({c.id for c in cards}), 5)

    def test_null_and_zero_are_distinct(self):
        cards = kpi_cards({"gross_revenue_amount": 0, "total_orders_count": 0})
        self.assertEqual(cards[0].children[1].children, "$0.00")
        self.assertEqual(cards[2].children[1].children, "—")
        self.assertEqual(cards[3].children[1].children, "0")

    def test_layout_does_not_query(self):
        with patch("pages.executive.load_executive_report") as query:
            layout()
            query.assert_not_called()

    def test_empty_and_error_preserve_five_cards(self):
        catalog = [
            {
                "calendar_year": 2013,
                "calendar_quarter_name": "Q1",
                "sales_channel": "Internet",
                "product_category": "Bikes",
                "product_subcategory": "Road Bikes",
            }
        ]
        empty = {
            "monthly": [],
            "detail": [],
            "gross_revenue_amount": 0,
            "total_orders_count": 0,
        }
        with patch("pages.executive.load_executive_report", return_value=empty):
            result = populate_report(
                catalog, "__all__", "__all__", "__all__", "__all__", "__all__", {}
            )
            self.assertEqual(len(result[0]), 5)
            self.assertIn("No warehouse sales", result[-1])
        with patch(
            "pages.executive.load_executive_report",
            side_effect=RuntimeError("private diagnostic"),
        ):
            result = populate_report(
                catalog, "__all__", "__all__", "__all__", "__all__", "__all__", {}
            )
            self.assertEqual(len(result[0]), 5)
            self.assertIn("Unable", result[-1])
            self.assertNotIn("private diagnostic", result[-1])

    def test_filter_validation(self):
        import dash

        catalog = [
            {
                "calendar_year": 2013,
                "calendar_quarter_name": "Q1",
                "sales_channel": "Internet",
                "product_category": "Bikes",
                "product_subcategory": "Road Bikes",
            },
            {
                "calendar_year": 2013,
                "calendar_quarter_name": "Q1",
                "sales_channel": "Reseller",
                "product_category": "Clothing",
                "product_subcategory": "Jerseys",
            },
        ]
        self.assertEqual(
            normalize_filters(
                catalog, "__all__", "__all__", "Internet", "Bikes", "Road Bikes"
            ),
            [None, None, "Internet", "Bikes", "Road Bikes"],
        )
        with self.assertRaises(dash.exceptions.PreventUpdate):
            normalize_filters(catalog, 2013, "Q1", "Internet", "Bikes", "Jerseys")
        with self.assertRaises(ValueError):
            normalize_filters(catalog, 2099, "Q1", "Internet", "Bikes", "Road Bikes")

    def test_rollup_uses_distinct_baskets_and_weighted_ratios(self):
        query = kpi_sql("test-project", "gold_adventureworks")
        self.assertIn("SELECT DISTINCT s.sales_channel, s.sales_order_number", query)
        self.assertNotIn("SUM(product_purchasing_orders_count)", query)
        self.assertIn("SAFE_DIVIDE(gross_profit_amount, gross_revenue_amount)", query)
        self.assertIn("SAFE_DIVIDE(gross_revenue_amount, total_orders_count)", query)


class MonthlyComboChartTests(unittest.TestCase):
    def test_weighted_margin_axes_and_zero_revenue(self):
        values = {
            "monthly": [
                {
                    "calendar_year": 2024,
                    "month_name": "February",
                    "sales_channel": "Internet",
                    "revenue": 0,
                    "profit": -10,
                },
                {
                    "calendar_year": 2024,
                    "month_name": "January",
                    "sales_channel": "Internet",
                    "revenue": 100,
                    "profit": 50,
                },
                {
                    "calendar_year": 2024,
                    "month_name": "January",
                    "sales_channel": "Reseller",
                    "revenue": 900,
                    "profit": 90,
                },
                {
                    "calendar_year": 2024,
                    "month_name": "March",
                    "sales_channel": "Internet",
                    "revenue": 200,
                    "profit": -20,
                },
            ],
            "detail": [],
            "fetched_at": "12:00 UTC",
        }
        chart = render_report(values, "dual")[1]
        original = render_report(values)[1]
        self.assertEqual(len(original.data), 1)
        self.assertEqual(original.data[0].type, "scatter")
        self.assertEqual(list(original.data[0].y), [1000, 0, 200])
        bars, line = chart.data
        self.assertEqual(bars.type, "bar")
        self.assertEqual(list(bars.y), [1000, 0, 200])
        self.assertEqual(line.type, "scatter")
        self.assertAlmostEqual(line.y[0], 14)
        self.assertIsNone(line.y[1])
        self.assertAlmostEqual(line.y[2], -10)
        self.assertEqual(line.yaxis, "y2")
        self.assertFalse(line.connectgaps)
        self.assertEqual(chart.layout.yaxis2.ticksuffix, "%")


class RevenueBreakdownTests(unittest.TestCase):
    def test_channel_shares_and_product_hierarchy(self):
        import pandas as pd
        from pages.executive import revenue_breakdown

        channels = pd.DataFrame(
            {"sales_channel": ["Internet", "Reseller"], "revenue": [100, 300]}
        )
        bars = revenue_breakdown(channels, [])
        self.assertTrue(all(trace.type == "bar" for trace in bars.data))
        self.assertEqual(sum(sum(trace.y) for trace in bars.data), 400)
        donut = revenue_breakdown(channels, [], "donut")
        self.assertEqual(list(donut.data[0].labels), ["B2C Internet", "B2B Reseller"])
        self.assertEqual(list(donut.data[0].values), [100, 300])
        self.assertEqual(donut.data[0].hole, 0.62)
        self.assertIn("$400.00", donut.layout.annotations[0].text)
        single = revenue_breakdown(channels.iloc[:1], [], "donut")
        self.assertIn("$100.00", single.layout.annotations[0].text)
        detail = [
            {
                "product_category": "Bikes",
                "product_subcategory": "Road",
                "revenue": 100,
            },
            {
                "product_category": "Bikes",
                "product_subcategory": "Road",
                "revenue": 200,
            },
            {
                "product_category": "Clothing",
                "product_subcategory": "Jerseys",
                "revenue": 100,
            },
        ]
        tree = revenue_breakdown(channels, detail, "treemap").data[0]
        totals = dict(zip(tree.ids, tree.values))
        self.assertEqual(totals["All products/Bikes/Road"], 300)
        self.assertEqual(totals["All products"], 400)
        empty = revenue_breakdown(channels, [], "treemap")
        self.assertEqual(len(empty.data), 0)
        self.assertIn("No positive revenue", empty.layout.annotations[0].text)


class YoyBadgeTests(unittest.TestCase):
    def test_ratios_margin_points_and_zero_baseline(self):
        from revenue_kpis import yoy_badge
        import dash_bootstrap_components as dbc

        values = {
            "revenue": 120,
            "margin": 12,
            "yoy": {
                "period": "2024 vs 2023",
                "previous": {"revenue": 100, "margin": 10},
            },
        }
        self.assertIsInstance(yoy_badge("revenue", "currency", values), dbc.Badge)
        self.assertEqual(
            yoy_badge("revenue", "currency", values).children, "↑ 20.0% YoY"
        )
        self.assertEqual(yoy_badge("margin", "percent", values).children, "↑ 2.0pp YoY")
        values["yoy"]["previous"]["revenue"] = 0
        self.assertEqual(yoy_badge("revenue", "currency", values).children, "YoY N/A")
        values["yoy"]["previous"]["revenue"] = 200
        self.assertEqual(
            yoy_badge("revenue", "currency", values).children, "↓ 40.0% YoY"
        )

    def test_comparison_keeps_filters_and_does_not_mutate_cached_result(self):
        from revenue_kpis import add_yoy_comparison

        current = {"source_rows": 1}
        with patch(
            "revenue_kpis.load_executive_report", return_value={"source_rows": 2}
        ) as query:
            result = add_yoy_comparison(
                current,
                "project",
                "dataset",
                2024,
                "Q2",
                "Internet",
                "Bikes",
                "Road Bikes",
            )
            query.assert_called_once_with(
                "project", "dataset", 2023, "Q2", "Internet", "Bikes", "Road Bikes"
            )
            self.assertIn("previous", result["yoy"])
            self.assertNotIn("yoy", current)
        with patch("revenue_kpis.load_executive_report") as query:
            result = add_yoy_comparison(
                current, "project", "dataset", None, None, None, None, None
            )
            query.assert_not_called()
            self.assertEqual(result["yoy"]["reason"], "Select year for YoY")
        with patch(
            "revenue_kpis.load_executive_report", return_value={"source_rows": 0}
        ):
            result = add_yoy_comparison(
                current, "project", "dataset", 2024, None, None, None, None
            )
            self.assertEqual(result["yoy"]["reason"], "No prior-year data")
        with patch(
            "revenue_kpis.load_executive_report", side_effect=RuntimeError("private")
        ):
            result = add_yoy_comparison(
                current, "project", "dataset", 2024, None, None, None, None
            )
            self.assertEqual(result["yoy"]["reason"], "YoY unavailable")

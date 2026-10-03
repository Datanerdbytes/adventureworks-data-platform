import re
import sqlite3
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from growth_kpis import (
    calculate_scorecards,
    growth_scorecards_sql,
    load_growth_scorecards,
)
from google.api_core.exceptions import NotFound
from pages.growth import populate_scorecards
from test_wholesale_kpis import ALL, CATALOG


def history():
    return dict(
        monthly=[
            dict(month=date(y, m, 1), revenue=v)
            for y, m, v in [
                (2025, 1, 100),
                (2025, 10, 100),
                (2026, 1, 200),
                (2026, 2, 400),
            ]
        ],
        anchor_date=date(2026, 2, 28),
        first_date=date(2025, 1, 1),
        rolling_revenue=400,
        order_velocity=2.5,
    )


class GrowthScorecardTests(unittest.TestCase):
    def test_historical_periods_and_peak(self):
        result = calculate_scorecards(history(), 2026, "Q1")
        self.assertEqual(result["qoq"], 500)
        self.assertEqual(result["yoy"], 500)
        self.assertAlmostEqual(float(result["peak"]), 4 / 3)
        self.assertEqual(result["rolling"], 400)
        self.assertEqual(result["velocity"], 2.5)
        self.assertEqual(calculate_scorecards(history(), 2026)["yoy"], 200)
        self.assertIn("2026Q1 vs 2025Q4", result["qoq_note"])

    def test_missing_history_zero_denominator_empty(self):
        data = history()
        data["monthly"] = data["monthly"][2:]
        data["first_date"] = date(2026, 2, 15)
        result = calculate_scorecards(data, 2026)
        self.assertIsNone(result["qoq"])
        self.assertIsNone(result["yoy"])
        self.assertIsNone(result["rolling"])
        self.assertIsNone(calculate_scorecards(data, 2024)["velocity"])
        data["monthly"][0]["revenue"] = 0
        data["monthly"][1]["revenue"] = 0
        self.assertIsNone(calculate_scorecards(data, 2026)["peak"])

    def test_callback_filter_scope_and_exact_labels(self):
        with (
            patch("pages.growth.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.growth.load_growth_scorecards", return_value=history()
            ) as loader,
        ):
            cards = populate_scorecards(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(
                loader.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            self.assertEqual(
                [c.children[0].children for c in cards],
                [
                    "QoQ Growth %",
                    "YoY Growth %",
                    "Rolling 30-Day Run Rate",
                    "Peak Seasonality Multiplier",
                    "Avg Daily Order Velocity",
                ],
            )
            loader.side_effect = RuntimeError("private")
            self.assertIn(
                "unavailable",
                populate_scorecards(CATALOG, *([ALL] * 5))[0].children[2].children,
            )

    def test_daily_invoice_grain_and_calendar_window(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales(order_date_key,product_key,sales_channel,sales_order_number,sales_amount);
        CREATE TABLE dim_date(date_key,calendar_date);
        CREATE TABLE dim_product(product_key,category_name,subcategory_name);
        INSERT INTO dim_date VALUES(1,'2026-01-01'),(2,'2026-01-30'),(3,'2026-01-31');
        INSERT INTO dim_product VALUES(1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO fct_sales VALUES(1,1,'Reseller','a',100),(2,1,'Reseller','b',20),(2,1,'Reseller','b',30),(2,1,'Internet','b',40),(3,2,'Reseller','c',10);
        """)
        sql = growth_scorecards_sql("p", "d", True)
        sql = (
            sql[: sql.index("), selected AS")]
            + ") SELECT d.order_date, d.orders, r.rolling_revenue FROM daily d JOIN rolling r USING(order_date) ORDER BY d.order_date"
        )
        sql = (
            re.sub(r"`p.d.(\w+)`", r"\1", sql)
            .replace(
                "COUNTIF(sales_order_number IS NOT NULL)",
                "SUM(sales_order_number IS NOT NULL)",
            )
            .replace("UNIX_DATE(order_date)", "julianday(order_date)")
        )
        params = dict(channel=None, category=None, subcategory=None)
        self.assertEqual(
            db.execute(sql, params).fetchall(),
            [("2026-01-01", 1, 100), ("2026-01-30", 2, 190), ("2026-01-31", 1, 100)],
        )
        self.assertEqual(
            db.execute(
                sql, {**params, "category": "Bikes", "channel": "Reseller"}
            ).fetchall(),
            [("2026-01-01", 1, 100), ("2026-01-30", 1, 150)],
        )


class GrowthSourceTests(unittest.TestCase):
    def test_missing_mart_falls_back_without_writes(self):
        with patch("growth_kpis.bigquery.Client") as client_type:
            client = client_type.return_value.__enter__.return_value
            client.get_table.side_effect = NotFound("missing mart")
            client.query.return_value.result.return_value = iter([history()])
            result = load_growth_scorecards.uncached("project", "dataset")
            self.assertIn("not deployed", result["source"])
            self.assertNotIn("marts_growth_trends", client.query.call_args.args[0])
            client.get_table.side_effect = None
            client.query.return_value.result.return_value = iter([history()])
            result = load_growth_scorecards.uncached("project", "dataset")
            self.assertEqual(result["source"], "Growth mart")
            self.assertIn("marts_growth_trends", client.query.call_args.args[0])

import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app as app  # Initializes Dash page/callback registration.
from growth_kpis import (
    calculate_scorecards,
    growth_daily_sql,
    load_growth_scorecards,
)
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


def daily_scalar_row():
    """One DuckDB row for the scalar-subquery day/grain summary."""
    row = dict(history())
    row.pop("monthly")
    return row


def fixture_db():
    """In-memory DuckDB copy of the artifact's gold sales tables."""
    db = duckdb.connect(":memory:")
    db.execute("""
        CREATE SCHEMA gold_adventureworks;
        CREATE TABLE gold_adventureworks.fct_sales(
            order_date_key INTEGER, product_key INTEGER, sales_channel VARCHAR,
            sales_order_number VARCHAR, sales_amount INTEGER);
        CREATE TABLE gold_adventureworks.dim_date(date_key INTEGER, calendar_date DATE);
        CREATE TABLE gold_adventureworks.dim_product(
            product_key INTEGER, category_name VARCHAR, subcategory_name VARCHAR);
        INSERT INTO gold_adventureworks.dim_date VALUES
            (1, DATE '2026-01-01'), (2, DATE '2026-01-30'), (3, DATE '2026-01-31'),
            (6, DATE '2025-10-15'), (7, DATE '2025-01-01');
        INSERT INTO gold_adventureworks.dim_product VALUES
            (1, 'Bikes', 'Road Bikes'), (2, 'Clothing', 'Jerseys');
        INSERT INTO gold_adventureworks.fct_sales VALUES
            (1, 1, 'Reseller', 'a', 100), (2, 1, 'Reseller', 'b', 20),
            (2, 1, 'Reseller', 'b', 30), (2, 1, 'Internet', 'b', 40),
            (3, 2, 'Reseller', 'c', 10), (6, 1, 'Reseller', 'd', 100),
            (7, 2, 'Internet', 'e', 100);
        """)
    return db


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
        db = fixture_db()
        self.addCleanup(db.close)
        # Keep the invoices/daily/rolling grain; the loader's own scalar
        # subqueries select the anchor rows behind $year/$quarter binds.
        sql = growth_daily_sql("p", "d")
        sql = (
            sql[: sql.index("), selected AS")]
            + ") SELECT d.order_date, d.orders, r.rolling_revenue"
            " FROM daily d JOIN rolling r USING(order_date) ORDER BY d.order_date"
        )
        self.assertEqual(
            db.execute(
                sql, dict(channel=None, category=None, subcategory=None)
            ).fetchall(),
            [
                (date(2025, 1, 1), 1, 100),
                (date(2025, 10, 15), 1, 100),
                (date(2026, 1, 1), 1, 100),
                (date(2026, 1, 30), 2, 190),
                (date(2026, 1, 31), 1, 100),
            ],
        )
        self.assertEqual(
            db.execute(
                sql,
                dict(channel="Reseller", category="Bikes", subcategory=None),
            ).fetchall(),
            [
                (date(2025, 10, 15), 1, 100),
                (date(2026, 1, 1), 1, 100),
                (date(2026, 1, 30), 1, 150),
            ],
        )

    def test_scalar_subqueries_bind_all_five_filters(self):
        db = fixture_db()
        self.addCleanup(db.close)
        self.assertEqual(
            db.execute(
                growth_daily_sql("p", "d"),
                dict(
                    year=None,
                    quarter=None,
                    channel=None,
                    category=None,
                    subcategory=None,
                ),
            ).fetchall(),
            [(date(2026, 1, 31), date(2025, 1, 1), 100, 1.2)],
        )
        anchor, first, rolling, velocity = db.execute(
            growth_daily_sql("p", "d"),
            dict(
                year=2026,
                quarter=None,
                channel=None,
                category=None,
                subcategory=None,
            ),
        ).fetchone()
        self.assertEqual(
            (anchor, first, rolling), (date(2026, 1, 31), date(2025, 1, 1), 100)
        )
        self.assertAlmostEqual(velocity, 4 / 3)
        anchor, first, rolling, velocity = db.execute(
            growth_daily_sql("p", "d"),
            dict(
                year=None,
                quarter="Q1",
                channel=None,
                category=None,
                subcategory=None,
            ),
        ).fetchone()
        self.assertEqual(
            (anchor, first, rolling), (date(2026, 1, 31), date(2025, 1, 1), 100)
        )
        self.assertAlmostEqual(velocity, 1.25)


class GrowthSourceTests(unittest.TestCase):
    def setUp(self):
        # Loaders memoize through the shared warehouse cache; give the covered
        # seam a disposable Flask app + cache, mirroring the other loader suites.
        from flask import Flask
        from growth_kpis import cache

        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        self.server = Flask("growth-source-tests")
        lock_dir = Path(directory) / "locks"
        lock_dir.mkdir()
        self.server.extensions["executive_query_lock_dir"] = lock_dir
        cache.init_app(
            self.server,
            config={"CACHE_TYPE": "FileSystemCache", "CACHE_DIR": directory},
        )

    @staticmethod
    def readings(source="Growth mart", calls=None):
        """Side effect mirroring load_growth_scorecards' three DuckDB reads."""

        def readings(sql, parameters=None):
            if calls is not None:
                calls.append((sql, parameters))
            if sql.startswith("SELECT 1 FROM"):
                # Mart availability probe: no parameters, low cost.
                if source == "missing":
                    raise Exception("growth mart missing")
                return [{"probe": True}]
            if "make_date(calendar_year" in sql:
                return [
                    {"month": row["month"], "revenue": row["revenue"]}
                    for row in history()["monthly"]
                ]
            if "date_trunc('month'" in sql:
                return [
                    {"month": row["month"], "revenue": row["revenue"]}
                    for row in history()["monthly"]
                ]
            if "anchor_date" in sql:
                return [daily_scalar_row()]
            raise AssertionError(f"Unexpected loader SQL: {sql[:80]!r}")

        return readings

    def test_missing_mart_falls_back_without_writes(self):
        calls = []
        with patch(
            "growth_kpis.query_rows", side_effect=self.readings("missing", calls)
        ):
            with self.server.app_context():
                result = load_growth_scorecards.uncached("project", "dataset")
        self.assertIn("not deployed", result["source"])
        self.assertEqual(result["monthly"], history()["monthly"])
        self.assertEqual(result["anchor_date"], date(2026, 2, 28))
        self.assertEqual(result["first_date"], date(2025, 1, 1))
        self.assertEqual(result["rolling_revenue"], 400)
        self.assertEqual(result["order_velocity"], 2.5)
        self.assertEqual(
            calls[0][0], "SELECT 1 FROM gold_adventureworks.marts_growth_trends LIMIT 1"
        )
        self.assertIsNone(calls[0][1])  # The probe binds no parameters.
        # Only the availability probe touched the missing mart: no data read and
        # no write went through it.
        self.assertEqual(len(calls), 3)
        for sql, parameters in calls[1:]:
            self.assertNotIn("marts_growth_trends", sql)

    def test_mart_source_binds_channel_only(self):
        calls = []
        with patch("growth_kpis.query_rows", side_effect=self.readings(calls=calls)):
            with self.server.app_context():
                result = load_growth_scorecards.uncached("project", "dataset")
        self.assertEqual(result["source"], "Growth mart")
        sql, parameters = calls[1]
        self.assertIn("make_date(calendar_year", sql)
        self.assertIn("marts_growth_trends", sql)
        self.assertEqual(parameters, {"channel": None})
        self.assertEqual(
            calls[2][1],
            {
                "year": None,
                "quarter": None,
                "channel": None,
                "category": None,
                "subcategory": None,
            },
        )

    def test_product_filters_rebuild_monthly_from_facts(self):
        calls = []
        with patch("growth_kpis.query_rows", side_effect=self.readings(calls=calls)):
            with self.server.app_context():
                result = load_growth_scorecards.uncached(
                    "project", "dataset", category="Bikes"
                )
        self.assertEqual(result["source"], "Product-filtered sales facts")
        # Product filters skip the mart probe entirely: no read may touch the
        # mart that has no product dimensions.
        self.assertTrue(
            all("marts_growth_trends" not in sql for sql, parameters in calls)
        )
        monthly_sql, monthly_parameters = calls[0]
        self.assertIn("date_trunc('month'", monthly_sql)
        self.assertEqual(
            monthly_parameters,
            {"channel": None, "category": "Bikes", "subcategory": None},
        )
        self.assertEqual(
            calls[1][1],
            {
                "year": None,
                "quarter": None,
                "channel": None,
                "category": "Bikes",
                "subcategory": None,
            },
        )

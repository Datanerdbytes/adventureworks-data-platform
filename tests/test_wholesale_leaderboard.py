"""Offline leaderboard ranking and callback coverage."""

import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.wholesale import populate_leaderboard, leaderboard_figure
from wholesale_kpis import top_resellers_sql
from test_wholesale_kpis import CATALOG, ALL


class LeaderboardTests(unittest.TestCase):
    def test_join_filter_aggregate_and_top_ten(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales (reseller_key, sales_channel, order_date_key, product_key, sales_amount);
        CREATE TABLE dim_reseller (reseller_key, reseller_name);
        CREATE TABLE dim_date (date_key, calendar_year, calendar_quarter_name);
        CREATE TABLE dim_product (product_key, category_name, subcategory_name);
        INSERT INTO dim_date VALUES (1, 2026, 'Q1'), (2, 2025, 'Q2');
        INSERT INTO dim_product VALUES (1, 'Bikes', 'Road Bikes'), (2, 'Clothing', 'Jerseys');
        """)
        db.executemany(
            "INSERT INTO dim_reseller VALUES (?, ?)",
            [(i, f"Reseller {i:02}") for i in range(1, 13)],
        )
        db.executemany(
            "INSERT INTO fct_sales VALUES (?, 'Reseller', 1, 1, ?)",
            [(i, i * 10) for i in range(1, 13)],
        )
        db.executescript("""
        INSERT INTO fct_sales VALUES (1, 'Reseller', 1, 1, 500), (1, 'Internet', 1, 1, 99999),
          (2, 'Reseller', 2, 2, 800), (99, 'Reseller', 1, 1, 99999);
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`", r"\1", top_resellers_sql("project", "dataset")
        )
        params = dict.fromkeys(
            ("year", "quarter", "channel", "category", "subcategory")
        )
        rows = db.execute(sql, params).fetchall()
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[:2], [("Reseller 02", 820), ("Reseller 01", 510)])
        self.assertEqual(
            [r[1] for r in rows], sorted([r[1] for r in rows], reverse=True)
        )
        for selected in (
            {"year": 2025},
            {"quarter": "Q2"},
            {"category": "Clothing"},
            {"subcategory": "Jerseys"},
            {
                "year": 2025,
                "quarter": "Q2",
                "channel": "Reseller",
                "category": "Clothing",
                "subcategory": "Jerseys",
            },
        ):
            self.assertEqual(
                db.execute(sql, {**params, **selected}).fetchall(),
                [("Reseller 02", 800)],
            )
        self.assertEqual(
            db.execute(sql, {**params, "channel": "Internet"}).fetchall(), []
        )
        self.assertEqual(db.execute(sql, {**params, "year": 1900}).fetchall(), [])

    def test_callback_filters_states_and_chart_order(self):
        rows = [
            {"reseller_name": "A", "revenue": 1200.25},
            {"reseller_name": "B", "revenue": 400},
        ]
        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch("pages.wholesale.load_top_resellers", return_value=rows) as query,
        ):
            figure, _ = populate_leaderboard(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(
                query.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            self.assertEqual(list(figure.layout.yaxis.categoryarray), ["B", "A"])
            self.assertEqual(figure.data[0].customdata[0][0], "$1,200.25")
            query.return_value = []
            figure, _ = populate_leaderboard(CATALOG, *[ALL] * 5)
            self.assertIn("No reseller sales", figure.layout.annotations[0].text)
            query.side_effect = RuntimeError("private diagnostic")
            figure, status = populate_leaderboard(CATALOG, *[ALL] * 5)
            self.assertEqual(
                figure.layout.annotations[0].text, "Leaderboard unavailable"
            )
            self.assertNotIn("private diagnostic", status)

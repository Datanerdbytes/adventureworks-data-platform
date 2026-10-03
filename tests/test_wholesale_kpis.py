"""Offline account-grain aggregation and wholesale callback checks."""

import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.wholesale import layout, populate_accounts
from sales_filters import ALL, valid_values
from wholesale_kpis import active_accounts_sql

CATALOG = [
    dict(
        calendar_year=2026,
        calendar_quarter_name="Q1",
        sales_channel="Reseller",
        product_category="Bikes",
        product_subcategory="Road Bikes",
    ),
    dict(
        calendar_year=2025,
        calendar_quarter_name="Q2",
        sales_channel="Internet",
        product_category="Clothing",
        product_subcategory="Jerseys",
    ),
]


class WholesaleKpiTests(unittest.TestCase):
    def setUp(self):
        comparison = patch(
            "pages.wholesale.load_wholesale_comparison", return_value={"source_rows": 0}
        )
        comparison.start()
        self.addCleanup(comparison.stop)

    def test_distinct_accounts_and_every_filter(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales (reseller_key, sales_order_number, sales_channel, order_date_key, product_key);
        CREATE TABLE dim_date (date_key, calendar_year, calendar_quarter_name);
        CREATE TABLE dim_product (product_key, category_name, subcategory_name);
        INSERT INTO dim_date VALUES (1, 2026, 'Q1'), (2, 2025, 'Q2');
        INSERT INTO dim_product VALUES (1, 'Bikes', 'Road Bikes'), (2, 'Clothing', 'Jerseys');
        INSERT INTO fct_sales VALUES
          (10, 'A', 'Reseller', 1, 1), (10, 'A', 'Reseller', 1, 1),
          (10, 'B', 'Reseller', 1, 2), (20, 'C', 'Reseller', 1, 1),
          (30, 'D', 'Reseller', 2, 2), (40, 'E', 'Internet', 1, 1),
          (NULL, 'F', 'Reseller', 1, 1), (50, NULL, 'Reseller', 1, 1);
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`", r"\1", active_accounts_sql("project", "dataset")
        )
        cases = [
            ({}, 3),
            ({"year": 2026}, 2),
            ({"quarter": "Q2"}, 1),
            ({"channel": "Internet"}, 0),
            ({"channel": "Reseller"}, 3),
            ({"category": "Clothing"}, 2),
            ({"subcategory": "Road Bikes"}, 2),
            (
                {
                    "year": 2026,
                    "quarter": "Q1",
                    "channel": "Reseller",
                    "category": "Clothing",
                    "subcategory": "Jerseys",
                },
                1,
            ),
            ({"year": 2024}, 0),
        ]
        for selections, expected in cases:
            with self.subTest(selections=selections):
                params = dict.fromkeys(
                    ("year", "quarter", "channel", "category", "subcategory")
                )
                params.update(selections)
                self.assertEqual(db.execute(sql, params).fetchone()[0], expected)

    def test_restored_and_dependent_values(self):
        _, values = valid_values(CATALOG, [2026, ALL, ALL, "Bikes", "Jerseys"])
        self.assertEqual(values, [2026, ALL, ALL, "Bikes", ALL])
        _, values = valid_values(CATALOG, [1900, "Bad", "Bad", ALL, "Jerseys"])
        self.assertEqual(values, [ALL, ALL, ALL, ALL, "Jerseys"])

    def test_callback_filters_zero_and_failure(self):
        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch("pages.wholesale.load_active_accounts", return_value=0) as query,
        ):
            card, status = populate_accounts(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(
                query.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            self.assertEqual(card.children[1].children, "0")
            self.assertIn("No wholesale accounts", status)
            query.side_effect = RuntimeError("private")
            card, status = populate_accounts(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertNotIn("private", status)

    def test_layout_is_lightweight(self):
        with (
            patch("pages.wholesale.load_active_accounts") as query,
            patch("pages.wholesale.load_filter_catalog") as catalog,
        ):
            tree = layout()
            query.assert_not_called()
            catalog.assert_not_called()
            self.assertIn("wholesale-account-kpi", str(tree))

    def test_revenue_sum_and_filters(self):
        from wholesale_kpis import reseller_revenue_sql

        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE revenue_sales_performance (calendar_year, calendar_quarter_name, sales_channel, product_category, product_subcategory, gross_revenue_amount);
        INSERT INTO revenue_sales_performance VALUES
          (2026, 'Q1', 'Reseller', 'Bikes', 'Road Bikes', 100.25),
          (2026, 'Q1', 'Reseller', 'Bikes', 'Road Bikes', 100.25),
          (2026, 'Q2', 'Reseller', 'Clothing', 'Jerseys', 50.5),
          (2025, 'Q1', 'Reseller', 'Bikes', 'Mountain Bikes', 200),
          (2026, 'Q1', 'Internet', 'Bikes', 'Road Bikes', 9000);
        ALTER TABLE revenue_sales_performance ADD COLUMN total_units_sold DEFAULT 0;
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`",
            r"\1",
            reseller_revenue_sql("project", "dataset"),
        )
        for filters, expected in [
            ({}, 451),
            ({"year": 2026}, 251),
            ({"quarter": "Q2"}, 50.5),
            ({"channel": "Internet"}, 0),
            ({"category": "Bikes"}, 400.5),
            ({"subcategory": "Road Bikes"}, 200.5),
            ({"year": 2024}, 0),
            (
                {
                    "year": 2026,
                    "quarter": "Q1",
                    "channel": "Reseller",
                    "category": "Bikes",
                    "subcategory": "Road Bikes",
                },
                200.5,
            ),
        ]:
            with self.subTest(filters=filters):
                params = dict.fromkeys(
                    ("year", "quarter", "channel", "category", "subcategory")
                )
                params.update(filters)
                self.assertEqual(db.execute(sql, params).fetchone()[0], expected)

    def test_revenue_callback_precision_empty_and_error(self):
        from decimal import Decimal
        from pages.wholesale import populate_revenue

        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.wholesale.load_reseller_revenue",
                return_value={
                    "total_reseller_revenue": Decimal("1234567.89"),
                    "source_rows": 3,
                },
            ) as query,
        ):
            card, status = populate_revenue(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(card.children[1].children, "$1.23M")
            self.assertEqual(
                query.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            query.return_value = {"total_reseller_revenue": 0, "source_rows": 0}
            card, status = populate_revenue(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "$0.00")
            self.assertIn("No reseller sales", status)
            self.assertEqual(query.call_args.args[2:], (None,) * 5)
            query.side_effect = RuntimeError("private diagnostic")
            card, status = populate_revenue(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertNotIn("private diagnostic", status)

    def test_average_uses_same_filters_and_unrounded_totals(self):
        from decimal import Decimal
        from pages.wholesale import populate_average

        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch("pages.wholesale.load_active_accounts", return_value=3) as accounts,
            patch(
                "pages.wholesale.load_reseller_revenue",
                return_value={
                    "total_reseller_revenue": Decimal("100.015"),
                    "source_rows": 4,
                },
            ) as revenue,
        ):
            card, _ = populate_average(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(card.children[1].children, "$33.34")
            self.assertEqual(accounts.call_args, revenue.call_args)
            self.assertEqual(
                accounts.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            revenue.return_value = {
                "total_reseller_revenue": Decimal("0"),
                "source_rows": 4,
            }
            card, _ = populate_average(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "$0.00")
            self.assertEqual(accounts.call_args.args[2:], (None,) * 5)
            accounts.return_value = 0
            card, status = populate_average(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertIn("zero", status)
            accounts.return_value = 3
            revenue.side_effect = RuntimeError("private diagnostic")
            card, status = populate_average(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertNotIn("private diagnostic", status)

    def test_average_waits_for_valid_filters(self):
        from dash.exceptions import PreventUpdate
        from pages.wholesale import populate_average

        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch("pages.wholesale.load_active_accounts") as query,
        ):
            card, _ = populate_average(None, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            with self.assertRaises(PreventUpdate):
                populate_average(CATALOG, 2026, "Q1", "Reseller", "Bikes", "Jerseys")
            query.assert_not_called()

    def test_wholesale_units_sum_and_filters(self):
        from wholesale_kpis import reseller_revenue_sql

        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE revenue_sales_performance (calendar_year, calendar_quarter_name, sales_channel, product_category, product_subcategory, gross_revenue_amount, total_units_sold);
        INSERT INTO revenue_sales_performance VALUES
          (2026, 'Q1', 'Reseller', 'Bikes', 'Road Bikes', 100, 12),
          (2026, 'Q1', 'Reseller', 'Bikes', 'Road Bikes', 100, 12),
          (2026, 'Q2', 'Reseller', 'Clothing', 'Jerseys', 50, 30),
          (2025, 'Q1', 'Reseller', 'Bikes', 'Mountain Bikes', 200, 5),
          (2026, 'Q1', 'Internet', 'Bikes', 'Road Bikes', 9000, 9999);
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`",
            r"\1",
            reseller_revenue_sql("project", "dataset"),
        )
        for filters, expected in [
            ({}, 59),
            ({"year": 2026}, 54),
            ({"quarter": "Q2"}, 30),
            ({"channel": "Internet"}, 0),
            ({"channel": "Reseller"}, 59),
            ({"category": "Bikes"}, 29),
            ({"subcategory": "Road Bikes"}, 24),
            ({"year": 2024}, 0),
            (
                {
                    "year": 2026,
                    "quarter": "Q1",
                    "channel": "Reseller",
                    "category": "Bikes",
                    "subcategory": "Road Bikes",
                },
                24,
            ),
        ]:
            with self.subTest(filters=filters):
                params = dict.fromkeys(
                    ("year", "quarter", "channel", "category", "subcategory")
                )
                params.update(filters)
                self.assertEqual(db.execute(sql, params).fetchone()[1], expected)

    def test_units_callback_values_and_states(self):
        from pages.wholesale import populate_units
        from dash.exceptions import PreventUpdate

        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.wholesale.load_reseller_revenue",
                return_value={"total_wholesale_units_sold": 1234567, "source_rows": 3},
            ) as query,
        ):
            card, _ = populate_units(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(card.children[1].children, "1.23M")
            self.assertEqual(
                query.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            query.return_value = {"total_wholesale_units_sold": 0, "source_rows": 0}
            card, status = populate_units(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "0")
            self.assertIn("No reseller sales", status)
            self.assertEqual(query.call_args.args[2:], (None,) * 5)
            query.reset_mock()
            card, _ = populate_units(None, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            with self.assertRaises(PreventUpdate):
                populate_units(CATALOG, 2026, "Q1", "Reseller", "Bikes", "Jerseys")
            query.assert_not_called()
            query.side_effect = RuntimeError("private diagnostic")
            card, status = populate_units(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertNotIn("private diagnostic", status)

    def test_wholesale_orders_are_distinct_across_product_lines(self):
        from wholesale_kpis import wholesale_orders_sql

        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales (sales_order_number, sales_channel, order_date_key, product_key);
        CREATE TABLE dim_date (date_key, calendar_year, calendar_quarter_name);
        CREATE TABLE dim_product (product_key, category_name, subcategory_name);
        INSERT INTO dim_date VALUES (1, 2026, 'Q1'), (2, 2025, 'Q2');
        INSERT INTO dim_product VALUES (1, 'Bikes', 'Road Bikes'), (2, 'Clothing', 'Jerseys');
        INSERT INTO fct_sales VALUES
          ('A', 'Reseller', 1, 1), ('A', 'Reseller', 1, 2), ('B', 'Reseller', 1, 1),
          ('C', 'Reseller', 2, 2), ('A', 'Internet', 1, 1), (NULL, 'Reseller', 1, 1);
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`",
            r"\1",
            wholesale_orders_sql("project", "dataset"),
        )
        for filters, expected in [
            ({}, 3),
            ({"year": 2026}, 2),
            ({"quarter": "Q2"}, 1),
            ({"channel": "Internet"}, 0),
            ({"category": "Clothing"}, 2),
            ({"subcategory": "Road Bikes"}, 2),
            ({"year": 2024}, 0),
            (
                {
                    "year": 2026,
                    "quarter": "Q1",
                    "channel": "Reseller",
                    "category": "Clothing",
                    "subcategory": "Jerseys",
                },
                1,
            ),
        ]:
            with self.subTest(filters=filters):
                params = dict.fromkeys(
                    ("year", "quarter", "channel", "category", "subcategory")
                )
                params.update(filters)
                self.assertEqual(db.execute(sql, params).fetchone()[0], expected)

    def test_aov_uses_total_revenue_and_distinct_orders(self):
        from decimal import Decimal
        from pages.wholesale import populate_aov
        from dash.exceptions import PreventUpdate

        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch("pages.wholesale.load_wholesale_orders", return_value=3) as orders,
            patch(
                "pages.wholesale.load_reseller_revenue",
                return_value={
                    "total_reseller_revenue": Decimal("100.015"),
                    "source_rows": 4,
                },
            ) as revenue,
        ):
            card, _ = populate_aov(
                CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            self.assertEqual(card.children[1].children, "$33.34")
            self.assertEqual(orders.call_args, revenue.call_args)
            self.assertEqual(
                orders.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            revenue.return_value = {"total_reseller_revenue": 0, "source_rows": 4}
            card, _ = populate_aov(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "$0.00")
            orders.return_value = 0
            card, status = populate_aov(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertIn("zero", status)
            orders.return_value = 3
            revenue.side_effect = RuntimeError("private diagnostic")
            card, status = populate_aov(CATALOG, *[ALL] * 5)
            self.assertEqual(card.children[1].children, "—")
            self.assertNotIn("private diagnostic", status)
            orders.reset_mock()
            populate_aov(None, *[ALL] * 5)
            with self.assertRaises(PreventUpdate):
                populate_aov(CATALOG, 2026, "Q1", "Reseller", "Bikes", "Jerseys")
            orders.assert_not_called()

    def test_yoy_badge_matches_executive_and_preserves_filters(self):
        import dash_bootstrap_components as dbc
        from pages.wholesale import average_card, with_yoy

        previous = {"source_rows": 3, "revenue_per_reseller": 100}
        with patch(
            "pages.wholesale.load_wholesale_comparison", return_value=previous
        ) as query:
            card = with_yoy(
                average_card(125, ""),
                "revenue_per_reseller",
                125,
                ("project", "dataset"),
                [2026, "Q1", "Reseller", "Bikes", "Road Bikes"],
                True,
            )
            self.assertEqual(card.children[0].children, "Revenue per Reseller")
            self.assertIsInstance(card.children[-1], dbc.Badge)
            self.assertEqual(card.children[-1].children, "↑ 25.0% YoY")
            self.assertEqual(
                query.call_args.args,
                ("project", "dataset", 2025, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            previous["revenue_per_reseller"] = 0
            card = with_yoy(
                average_card(125, ""),
                "revenue_per_reseller",
                125,
                ("project", "dataset"),
                [2026, ALL, ALL, ALL, ALL],
                True,
            )
            self.assertEqual(card.children[-1].children, "YoY N/A")
            query.reset_mock()
            card = with_yoy(
                average_card(125, ""),
                "revenue_per_reseller",
                125,
                ("project", "dataset"),
                [ALL] * 5,
                True,
            )
            self.assertEqual(card.children[-1].children, "Select year for YoY")
            query.assert_not_called()
            query.side_effect = RuntimeError("private")
            card = with_yoy(
                average_card(125, ""),
                "revenue_per_reseller",
                125,
                ("project", "dataset"),
                [2026, ALL, ALL, ALL, ALL],
                True,
            )
            self.assertEqual(card.children[1].children, "$125.00")
            self.assertEqual(card.children[-1].children, "YoY unavailable")

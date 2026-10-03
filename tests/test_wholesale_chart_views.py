"""Warehouse chart grains, filter scope, and view switching."""

import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.wholesale import populate_secondary
from wholesale_kpis import reseller_scatter_sql, wholesale_product_mix_sql
from test_wholesale_kpis import CATALOG, ALL


class WholesaleChartViewTests(unittest.TestCase):
    def test_scatter_grain_and_filters(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE fct_sales (reseller_key, sales_channel, order_date_key, product_key, order_quantity);
        CREATE TABLE dim_reseller (reseller_key, reseller_name, annual_revenue);
        CREATE TABLE dim_date (date_key, calendar_year, calendar_quarter_name);
        CREATE TABLE dim_product (product_key, category_name, subcategory_name);
        INSERT INTO dim_reseller VALUES (1, 'Same name', 100000), (2, 'Same name', 200000), (3, 'Missing revenue', NULL);
        INSERT INTO dim_date VALUES (1, 2026, 'Q1'), (2, 2025, 'Q2');
        INSERT INTO dim_product VALUES (1, 'Bikes', 'Road Bikes'), (2, 'Clothing', 'Jerseys');
        INSERT INTO fct_sales VALUES (1,'Reseller',1,1,10), (1,'Reseller',1,1,15),
          (2,'Reseller',2,2,40), (3,'Reseller',1,1,99), (1,'Internet',1,1,999);
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`",
            r"\1",
            reseller_scatter_sql("project", "dataset"),
        )
        params = dict.fromkeys(
            ("year", "quarter", "channel", "category", "subcategory")
        )
        self.assertEqual(
            db.execute(sql, params).fetchall(),
            [(1, "Same name", 100000, 25), (2, "Same name", 200000, 40)],
        )
        for selection in (
            {"year": 2026},
            {"quarter": "Q1"},
            {"category": "Bikes"},
            {"subcategory": "Road Bikes"},
            {
                "year": 2026,
                "quarter": "Q1",
                "channel": "Reseller",
                "category": "Bikes",
                "subcategory": "Road Bikes",
            },
        ):
            self.assertEqual(
                db.execute(sql, {**params, **selection}).fetchall(),
                [(1, "Same name", 100000, 25)],
            )
        self.assertEqual(
            db.execute(sql, {**params, "channel": "Internet"}).fetchall(), []
        )

    def test_product_mix_warehouse_aggregation(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE revenue_sales_performance (calendar_year, calendar_quarter_name, sales_channel, product_category, product_subcategory, gross_revenue_amount);
        INSERT INTO revenue_sales_performance VALUES
        (2026,'Q1','Reseller','Bikes','Road Bikes',100),
        (2026,'Q1','Reseller','Bikes','Mountain Bikes',50),
        (2025,'Q2','Reseller','Clothing','Jerseys',40),
        (2026,'Q1','Internet','Bikes','Road Bikes',9999);
        """)
        sql = re.sub(
            r"`project.dataset.(\w+)`",
            r"\1",
            wholesale_product_mix_sql("project", "dataset"),
        )
        params = dict.fromkeys(
            ("year", "quarter", "channel", "category", "subcategory")
        )
        self.assertEqual(
            db.execute(sql, params).fetchall(), [("Bikes", 150), ("Clothing", 40)]
        )
        for selection in ({"year": 2026}, {"quarter": "Q1"}, {"category": "Bikes"}):
            self.assertEqual(
                db.execute(sql, {**params, **selection}).fetchall(), [("Bikes", 150)]
            )
        self.assertEqual(
            db.execute(sql, {**params, "subcategory": "Road Bikes"}).fetchall(),
            [("Bikes", 100)],
        )
        self.assertEqual(
            db.execute(sql, {**params, "channel": "Internet"}).fetchall(), []
        )

    def test_only_active_view_queries_and_axes_are_truthful(self):
        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.wholesale.load_wholesale_product_mix",
                return_value=[{"product_category": "Bikes", "revenue": 1234.5}],
            ) as mix,
            patch(
                "pages.wholesale.load_reseller_scatter",
                return_value=[
                    {
                        "reseller_name": "A",
                        "reseller_key": 1,
                        "annual_revenue": 100000,
                        "total_units_sold": 25,
                    }
                ],
            ) as scatter,
        ):
            figure, title, status = populate_secondary("bar", CATALOG, *[ALL] * 5)
            self.assertEqual(figure.data[0].type, "bar")
            self.assertEqual(figure.data[0].customdata[0][0], "$1,234.50")
            scatter.assert_not_called()
            mix.reset_mock()
            figure, title, status = populate_secondary(
                "scatter", CATALOG, 2026, "Q1", "Reseller", "Bikes", "Road Bikes"
            )
            mix.assert_not_called()
            self.assertEqual(
                scatter.call_args.args[2:],
                (2026, "Q1", "Reseller", "Bikes", "Road Bikes"),
            )
            self.assertEqual(figure.data[0].type, "scatter")
            self.assertEqual(
                figure.layout.xaxis.title.text, "Reseller annual revenue (USD)"
            )
            self.assertEqual(figure.layout.yaxis.title.text, "Units sold")
            scatter.return_value = []
            figure, _, _ = populate_secondary("scatter", CATALOG, *[ALL] * 5)
            self.assertIn("No reseller sales", figure.layout.annotations[0].text)
            scatter.side_effect = RuntimeError("private")
            figure, _, status = populate_secondary("scatter", CATALOG, *[ALL] * 5)
            self.assertNotIn("private", status)
            self.assertEqual(figure.layout.annotations[0].text, "Chart unavailable")

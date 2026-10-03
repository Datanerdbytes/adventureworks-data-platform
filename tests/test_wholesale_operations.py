import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.wholesale import populate_operations, operations_columns
from wholesale_kpis import wholesale_operations_sql
from test_wholesale_kpis import CATALOG, ALL


class OperationsTests(unittest.TestCase):
    def test_invoice_grain_filters_and_missing_shipping(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
        CREATE TABLE stg_fact_reseller_sales(reseller_key, sales_order_number, order_quantity, ship_date, order_date, order_date_key, product_key);
        CREATE TABLE dim_date(date_key, calendar_year, calendar_quarter_name);
        CREATE TABLE dim_product(product_key, category_name, subcategory_name);
        CREATE TABLE dim_reseller(reseller_key,reseller_name,order_frequency,state_province_name,country_region_name);
        INSERT INTO dim_date VALUES(1,2026,'Q1'),(2,2025,'Q2');
        INSERT INTO dim_product VALUES(1,'Bikes','Road Bikes'),(2,'Clothing','Jerseys');
        INSERT INTO dim_reseller VALUES(1,' Buyer ','A','CA','USA'),(2,'Buyer','Q','BC','Canada');
        INSERT INTO stg_fact_reseller_sales VALUES
        (1,'a',10,'2026-01-09','2026-01-01',1,1),
        (1,'a',20,'2026-01-09','2026-01-01',1,1),
        (1,'b',6,'2026-01-03','2026-01-01',1,1),
        (1,'c',4,NULL,'2026-01-01',1,1),
        (2,'d',9,'2025-01-08','2025-01-01',2,2);
        """)
        sql = wholesale_operations_sql("project", "gold", "silver")
        sql = re.sub(r"`project.\w+.(\w+)`", r"\1", sql)
        sql = sql.replace(
            "DATE_DIFF(s.ship_date, s.order_date, DAY)",
            "julianday(s.ship_date) - julianday(s.order_date)",
        ).replace("SUM(i.units) / COUNT(*)", "1.0 * SUM(i.units) / COUNT(*)")
        params = dict.fromkeys(
            ("year", "quarter", "channel", "category", "subcategory")
        )
        rows = db.execute(sql, params).fetchall()
        self.assertEqual(len(rows), 2)
        row = next(r for r in rows if r[0] == 1)
        self.assertEqual(row[3], 3)
        self.assertAlmostEqual(row[4], 40 / 3)
        self.assertEqual(row[5], 5)  # Per invoice, not the line-weighted 6 days.
        for filters in (
            {"year": 2026},
            {"quarter": "Q1"},
            {"category": "Bikes"},
            {"subcategory": "Road Bikes"},
        ):
            self.assertEqual(len(db.execute(sql, {**params, **filters}).fetchall()), 1)
        self.assertEqual(
            db.execute(sql, {**params, "channel": "Internet"}).fetchall(), []
        )

    def test_callback_labels_empty_error_and_alert(self):
        args = (CATALOG, ALL, ALL, ALL, ALL, ALL)
        row = dict(
            reseller_name="Buyer",
            order_frequency="A",
            total_orders_count=2,
            average_units_per_order=10,
            average_shipping_lead_days=6,
            state_province_name="CA",
            country_region_name="USA",
        )
        with (
            patch("pages.wholesale.load_filter_catalog", return_value=CATALOG),
            patch(
                "pages.wholesale.load_wholesale_operations", return_value=[row]
            ) as loader,
        ):
            records, status = populate_operations(*args)
            self.assertEqual(records[0]["order_frequency"], "Monthly")
            self.assertEqual(records[0]["territory"], "CA / USA")
            self.assertEqual(row["order_frequency"], "A")
            loader.return_value = []
            self.assertIn("No reseller", populate_operations(*args)[1])
            loader.side_effect = RuntimeError("private error")
            self.assertNotIn("private", populate_operations(*args)[1])
        columns = operations_columns()
        self.assertEqual(len(columns), 6)
        self.assertIn(
            "params.value > 5", columns[4]["cellClassRules"]["wholesale-lead-alert"]
        )
